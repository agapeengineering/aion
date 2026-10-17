# Third-party notices

Aion's original source is MIT licensed. Runtime dependencies retain their licenses:

- React and React DOM, version 19.3.1 — MIT, copyright Meta Platforms, Inc. and affiliates. Bundled notices: [React](apps/web/public/licenses/react-MIT.txt) and [React DOM](apps/web/public/licenses/react-dom-MIT.txt).
- Inter, distributed by `@fontsource/inter` 5.3.0 — SIL Open Font License 1.1. [Bundled license](apps/web/public/licenses/inter-OFL.txt).
- Geist Mono, distributed by `@fontsource/geist-mono` 5.3.0 — SIL Open Font License 1.1. [Bundled license](apps/web/public/licenses/geist-mono-OFL.txt).

Fonts are self-hosted; no Google Fonts request is made. The interface's Georgia serif uses an existing system font and does not redistribute it. The bilingual phrase bank is original project content. There are no attributed third-party quotations or image assets.

Tooling dependencies are pinned in the workspace lockfile and retain their package licenses; no ownership claim is made over them. Run `pnpm audit --prod` for the runtime vulnerability check and review notices when dependencies/assets change.
