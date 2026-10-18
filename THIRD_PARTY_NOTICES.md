# Third-party notices

Aion's original source is MIT licensed. Runtime dependencies retain their licenses:

- React and React DOM, version 19.3.1 — MIT, copyright Meta Platforms, Inc. and affiliates. Bundled notices: [React](apps/web/public/licenses/react-MIT.txt) and [React DOM](apps/web/public/licenses/react-dom-MIT.txt).
- Inter, distributed by `@fontsource/inter` 5.3.0 — SIL Open Font License 1.1. [Bundled license](apps/web/public/licenses/inter-OFL.txt).
- Geist Mono, distributed by `@fontsource/geist-mono` 5.3.0 — SIL Open Font License 1.1. [Bundled license](apps/web/public/licenses/geist-mono-OFL.txt).

Fonts are self-hosted; no Google Fonts request is made. The interface's Georgia serif uses an existing system font and does not redistribute it. The bilingual phrase bank is original project content. There are no attributed third-party quotations or image assets.

Tooling dependencies are pinned in the workspace lockfile and retain their package licenses; no ownership claim is made over them. Run `pnpm audit --prod` for the runtime vulnerability check and review notices when dependencies/assets change.

## Local backend foundation

Python runtime dependencies are separately pinned in `apps/backend/uv.lock`. Their package metadata/license files are retained in the installed environment and copied into the backend image, rather than relicensed under Aion's MIT license. FastAPI, SQLAlchemy, Alembic and Pydantic retain their upstream terms; Starlette/Uvicorn and all transitive dependencies retain theirs. Psycopg is LGPL-3.0 licensed; its binary distribution includes third-party libraries with their own notices. Container base images also retain their OS/runtime licenses. Before publishing/distributing backend images, review packaged notices and source/relinking obligations for the actual pinned image contents; a dependency audit is not a license review. The foundation's images are currently local development artifacts, not published binaries.

The local authentication slice adds `cryptography` 50.0.2 (Apache-2.0 OR BSD-3-Clause) and `email-validator` 2.3.0 (Unlicense), with transitive package notices preserved in the installed environment/image. The development capture image Mailpit retains its MIT license and bundled dependency terms; it is not included in the public web build.

Database documentation uses ERAlchemy 1.7.0 (Apache-2.0) and the Python graphviz development dependency (MIT). The separately installed Graphviz executable retains its upstream license. These development tools are not included in the production backend image; generated schema documentation uses local rendering.
