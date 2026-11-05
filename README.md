# Gensite

A Windows desktop workspace for generating, editing, previewing and publishing static websites to GitHub Pages.

<img width="1919" height="1078" alt="image" src="https://github.com/user-attachments/assets/f0c2a89d-bdf3-4b78-bff6-a317d88a01f4" />

<img width="1919" height="1079" alt="image" src="https://github.com/user-attachments/assets/44855833-1076-42a7-b93e-20df6032237f" />

**Version 1.0** · [Releases](https://github.com/marduk191/Gensite/releases) · `python -m gensite --version`

- Describe a site in the app. A text model writes the pages (existing [Hermes](https://hermes-agent.nousresearch.com/) install, or any local OpenAI-compatible endpoint). Your local [ComfyUI](https://github.com/comfyanonymous/ComfyUI) generates the images.
- Pick one of 51 original page templates to steer the design. Selecting a template previews it live; **Custom** restores the opening artwork.
- Edit visually (text, color, size, padding, images) or in source, then preview the saved files over HTTP with GitHub Pages-style repository paths.
- Publish from inside the app with an explicit `owner/repository` and public confirmation.

## Install and run

Requires Windows and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```
git clone https://github.com/marduk191/Gensite.git
cd Gensite
"Start Gensite.bat"
```

The first run creates `.venv` (Python 3.12) and installs `requirements.txt` (PySide6). `Start Gensite.bat --check` verifies the runtime without opening a window.

Then open **Settings** and set:

- **Hermes executable**. To use a local OpenAI-compatible server instead, set **Text model** under *Generation options* to its URL.
- **ComfyUI URL** (default `http://127.0.0.1:8188`). Start ComfyUI before requesting images.
- **ComfyUI API workflow**. The default is bundled in `workflows/`; [workflows/README.md](workflows/README.md) lists the custom nodes and model files it needs.

`settings.example.json` shows every field. `settings.json` and `projects/` are created locally and are never committed.

## Create a site

1. Choose **New**, enter the website name and describe what you want.
2. Choose **Custom** or a page template. **Preview template** shows the example page without replacing your project.
3. Open **Generation options** for style, image count and image art direction.
4. Select **Generate website**. A progress panel opens at the bottom while the job runs; **Cancel job** stops only that job, and **Close** dismisses the log afterwards.
5. Generated source and assets are saved in `projects/<job>/site/`.

## Edit and preview

- **Edit:** select a page element, change it in the inspector, apply and save. Backups are kept outside the website source.
- **Code:** edit source directly.
- **Revise:** ask for larger changes using the current site as context, for one element or the whole site. Revisions produce a new project.
- **Preview:** runs the saved site without editing helpers, using a local HTTP repository subpath and case-sensitive file lookup, at desktop, tablet and mobile widths.

Preview matches static GitHub Pages URL and file behavior. It does not emulate GitHub's build infrastructure, CDN, custom domains or account policies.

## Publish to GitHub Pages

Use **Publish**, enter `owner/repository` (a pasted GitHub URL is fine), check GitHub readiness and confirm public publication. A new public repository is created only if you select the create option. Publishing updates a separate `gensite-pages` branch without force-pushing or touching the default branch.

Publishing uses your existing `gh` authentication. The app verifies the remote settings and the deployed index before reporting a site as published; while GitHub is still building it reports "deploying".

## Layout

```
Start Gensite.bat     launcher (creates .venv, runs python -m gensite)
gensite/              application package
  engine.py             Hermes / local-model and ComfyUI pipeline
  native_app.py         Qt workflows, editor, inspector, workers
  native_canvas.py      lazy browser canvas and editing helpers
  native_preview.py     loopback read-only static server
  publisher.py          preflight, isolated git operations, Pages verification
  preset_catalog.py     template catalog loader
  ...                   reference reader, clone, research and recovery helpers
presets/              template catalog and runnable template pages
workflows/            default ComfyUI API workflow
assets/               application artwork
```

## Limits

Element and property editing plus a source editor; no drag-and-drop layout construction and no visual undo stack. Text replacement can replace nested inline markup, and dynamic page scripts can affect the serialized DOM, so use source editing when you need exact control. Image generation needs a ComfyUI install with the nodes and models listed in `workflows/README.md`.

This was developed on qwen flash next on an RTX 3060 12GB using the strata project here: https://github.com/Niko1221/Strata

<img width="569" height="340" alt="image" src="https://github.com/user-attachments/assets/d50d4d25-71f2-44b4-8c3a-a8c40964ca7e" />


## Support

The header has a **Support development** button that opens a donation page with multiple services that process payments including ko-fi, cashapp, paypal, and multiple SOLANA network chains for bitcoin, solana, and etherium.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Sites and images you generate are yours; the bundled templates and artwork are covered by the same license unless a file states otherwise.
