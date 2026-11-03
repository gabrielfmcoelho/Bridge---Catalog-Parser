"""Mermaid diagram of one repository: its CI, its components, and how they link to other CIs.

Arrow direction is dependency direction: `A --> B` means A depends on B. Output is deterministic
(no timestamps), so regenerating without catalog changes leaves no diff."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .config import DiagramSettings, Layout, Settings, Vocabulary
from .issues import WARNING, Issue, RuleInfo
from .kinds import DEPENDENCIES
from .linter import Linter
from .models import DEFAULT_VOCABULARY, Component, Dependency, DependencyCatalog
from .repository import PeerLoader, Repository

NO_DOCS = RuleInfo("W301", WARNING, "docs folder not found: diagram not written")


def _id(*parts: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", "_".join(parts)).strip("_")


def _q(text: str) -> str:
    return str(text).replace('"', "'")


def _endpoint(protocol: str | None, port: int | None) -> str:
    proto = protocol or ""
    return f"{proto}:{port}" if port else proto


def _component_text(c: Component) -> str:
    ep = _endpoint(c.protocol, c.port)
    return f"{c.name}<br/>{c.technology}" + (f" · {ep}" if ep else "")


class MermaidRenderer:
    """Flowchart source of one catalog. `peers` only enrich the labels of components other CIs provide."""

    def __init__(self, settings: DiagramSettings | None = None, vocabulary: Vocabulary = DEFAULT_VOCABULARY):
        self.settings = settings or DiagramSettings()
        self.vocabulary = vocabulary

    def _shape(self, node_id: str, text: str, category: str | None = None) -> str:
        if self.vocabulary.is_data(category):
            return f'{node_id}[("{_q(text)}")]'
        return f'{node_id}["{_q(text)}"]'

    def render(self, own: DependencyCatalog, peers: Iterable[DependencyCatalog] = ()) -> str:
        known = {p.ci: {c.name: c for c in p.components} for p in peers}
        own_components = {c.name: c for c in own.components}
        classes: dict[str, list[str]] = {}
        out = [f"flowchart {self.settings.direction}"]

        def component_node(ci: str, c: Component) -> str:
            nid = _id(ci, c.name)
            classes.setdefault(c.criticality, []).append(nid)
            return "    " + self._shape(nid, _component_text(c), c.category)

        own_id = _id("ci", own.ci)
        out.append(f'  subgraph {own_id}["{_q(own.ci)}"]')
        out += [component_node(own.ci, c) for c in own.components]
        out.append("  end")

        provided: dict[str, list[str]] = {}   # other CI -> components of it that this CI links to
        plain: dict[str, Dependency] = {}     # CIs without component: externals, consumers without a catalog
        for dep in [*own.dependencies.upstream, *own.dependencies.downstream]:
            if dep.component:
                names = provided.setdefault(dep.ci, [])
                if dep.component not in names:
                    names.append(dep.component)
            else:
                plain.setdefault(dep.ci, dep)

        for ci, names in provided.items():
            out.append(f'  subgraph {_id("ci", ci)}["{_q(ci)}"]')
            for name in names:
                c = known.get(ci, {}).get(name)
                out.append(component_node(ci, c) if c else f'    {_id(ci, name)}["{_q(name)}"]')
            out.append("  end")

        for ci, dep in plain.items():
            nid = _id("ext", ci)
            text = ci
            if dep.technology:
                ep = _endpoint(dep.protocol, dep.port)
                text += f"<br/>{dep.technology}" + (f" · {ep}" if ep else "")
            out.append(f'  {nid}(["{_q(text)}"])')
            if dep.criticality:
                classes.setdefault(dep.criticality, []).append(nid)

        def own_end(name: str | None) -> str:
            return _id(own.ci, name) if name in own_components else own_id

        def edge(src: str, dst: str, endpoint: str, via: str | None) -> str:
            label = " · ".join(x for x in (endpoint, f"via {via}" if via else "") if x)
            return f'  {src} -->|"{_q(label)}"| {dst}' if label else f"  {src} --> {dst}"

        for dep in own.dependencies.upstream:  # this CI consumes
            if dep.component:
                c = known.get(dep.ci, {}).get(dep.component)
                dst, ep = _id(dep.ci, dep.component), (_endpoint(c.protocol, c.port) if c else "")
            else:
                dst, ep = _id("ext", dep.ci), _endpoint(dep.protocol, dep.port)
            out.append(edge(own_end(dep.local_component), dst, ep, dep.via))
        for dep in own.dependencies.downstream:  # the other CI consumes this one
            src = _id(dep.ci, dep.component) if dep.component else _id("ext", dep.ci)
            c = own_components.get(dep.local_component)
            out.append(edge(src, own_end(dep.local_component), _endpoint(c.protocol, c.port) if c else "", dep.via))

        styled = [crit for crit in self.vocabulary.criticalities if crit in classes and crit in self.settings.styles]
        if styled:
            out.append("")
            for crit in styled:
                out.append(f"  classDef {crit} {self.settings.styles[crit]}")
                out.append(f"  class {','.join(classes[crit])} {crit}")
        return "\n".join(out)


class MarkdownRenderer:
    """The page around the diagram: generated-file banner, title, description and legend."""

    def __init__(self, mermaid: MermaidRenderer, source: str = "catalog/dependencies.yml"):
        self.mermaid = mermaid
        self.source = source  # catalog path named in the banner

    def render(self, own: DependencyCatalog, peers: Iterable[DependencyCatalog] = ()) -> str:
        settings = self.mermaid.settings
        return f"""<!-- Generated by catalog-parser from {self.source}. Do not edit by hand. -->
# {settings.title.replace("{ci}", own.ci)}

{own.description}

```mermaid
{self.mermaid.render(own, peers)}
```

{settings.legend.rstrip()}
"""


@dataclass
class DiagramResult:
    path: Path | None = None            # file written, None when nothing was written
    markdown: str | None = None         # rendered content, None when the catalog could not be loaded
    issues: list[Issue] = field(default_factory=list)


class DiagramWriter:
    """Writes to `<root>/<docs_dir>/<subdir>/<filename>`. A missing docs folder is a W301 warning,
    never an error: nothing is written (and nothing is created). The subfolder is created on demand."""

    def __init__(self, settings: DiagramSettings | None = None):
        self.settings = settings or DiagramSettings()

    def write(self, repo_root: Path, markdown: str, result: DiagramResult) -> DiagramResult:
        docs = repo_root / self.settings.docs_dir
        if not docs.is_dir():
            result.issues.append(Issue(NO_DOCS.code, NO_DOCS.severity, f"docs folder '{docs}' not found; diagram not written", docs))
            return result
        target = docs / self.settings.subdir
        target.mkdir(parents=True, exist_ok=True)
        result.path = target / self.settings.filename
        result.path.write_text(markdown, encoding="utf-8")
        return result


class DiagramGenerator:
    """Loads a repository's catalog and its peers, renders the page and (optionally) writes it."""

    def __init__(self, linter: Linter, renderer: MarkdownRenderer | None = None, writer: DiagramWriter | None = None,
                 peer_loader: PeerLoader | None = None):
        settings = linter.settings
        self.linter = linter
        self.layout: Layout = settings.layout
        self.renderer = renderer or MarkdownRenderer(MermaidRenderer(settings.diagram, settings.vocabulary),
                                                     f"{self.layout.catalog_dir}/{DEPENDENCIES.filename}")
        self.writer = writer or DiagramWriter(settings.diagram)
        self.peer_loader = peer_loader or PeerLoader(linter)

    def generate(self, root: str | Path = ".", peers: Iterable[str | Path] | None = None, write: bool = True) -> DiagramResult:
        """An unreadable or schema-invalid catalog cannot be drawn: `markdown` stays None and the lint
        errors come back in `issues`."""
        repo = Repository(root, self.layout)
        file = repo.catalog_file(DEPENDENCIES.filename)
        own = self.linter.lint_file(file, DEPENDENCIES)
        if own.catalog is None:
            return DiagramResult(issues=own.issues)
        others = [p.catalog for p in self.peer_loader.load(peers, file, DEPENDENCIES) if p.catalog]
        result = DiagramResult(markdown=self.renderer.render(own.catalog, others))
        return self.writer.write(repo.root, result.markdown, result) if write else result


def render_mermaid(own: DependencyCatalog, peers: Iterable[DependencyCatalog] = (), settings: Settings | None = None) -> str:
    """Flowchart source (default settings unless given)."""
    settings = settings or Settings()
    return MermaidRenderer(settings.diagram, settings.vocabulary).render(own, peers)


def generate_diagram(
    root: str | Path = ".",
    peers: Iterable[str | Path] | None = None,
    docs_dir: str | None = None,
    subdir: str | None = None,
    filename: str | None = None,
    write: bool = True,
    settings: Settings | None = None,
) -> DiagramResult:
    """Render the diagram of the repository at `root` and write it to `<root>/<docs_dir>/<subdir>/<filename>`.
    Settings default to the config file found from `root`; `docs_dir`, `subdir` and `filename` override them."""
    settings = (settings or Settings.discover(root)).with_diagram(docs_dir=docs_dir, subdir=subdir, filename=filename)
    return DiagramGenerator(Linter(settings)).generate(root, peers, write)
