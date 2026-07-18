# Slide Library

Study-material slides, organized by topic, browsable in Mission Control at
`/slides` (🎞 button). Built for future presentations — keep everything
regenerable.

## How to add a slide

1. Pick (or create) a topic folder: `docs/slides/<topic-slug>/`.
   The slug becomes the section title (dashes → spaces, title-cased).
2. Drop the PNG in as `NN_short_name.png` — the `NN_` prefix sets the order
   within the topic.
3. Optional caption: a sidecar `NN_short_name.md` next to the PNG.
   First line = title shown under the thumbnail; remaining lines = notes
   shown in the expanded view.
4. Keep the render script in `<topic-slug>/src/` so the slide can be
   regenerated or restyled later.
5. Rebuild the gallery:  `.venv/Scripts/python.exe scripts/slides_build.py`
6. Commit the topic folder (PNGs are committed — they ARE the material).

Mission Control serves `docs/slides/index.html` at `/slides` and the images
statically at `/slides/<topic>/<file>` — no restart needed after a rebuild.
