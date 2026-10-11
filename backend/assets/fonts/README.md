# Fonts used by interpolation PDF exports

Noto Sans and Noto Sans SC are embedded and subset in exported PDFs. The bundled
SIL Open Font License files apply to each font. The application does not depend
on fonts installed on Windows or Render.

Downloaded from Google's font repository:

- [Noto Sans](https://github.com/google/fonts/tree/main/ofl/notosans)
- [Noto Sans SC](https://github.com/google/fonts/tree/main/ofl/notosanssc)

The variable fonts were instantiated at weight 400 and default width using
fontTools 4.66.1. The reserved font name `Source` is not used.

| File | Upstream SHA-256 | Bundled static SHA-256 |
| --- | --- | --- |
| NotoSans.ttf | bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d | 9f12a859f0b41dff79a12fc1438a9eec3dd777fc6b78f8ac979261d2b043b303 |
| NotoSansSC.ttf | a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da | a5eabb3d77bdfb3404bc3912223685d83e4af53fd0b9ddce7192a1c93e5e836b |

PDF names support Latin, Greek, Cyrillic, Chinese, and supported Japanese glyphs.
Names are checked against the embedded fonts before rendering. Unsupported
glyphs and scripts requiring right-to-left shaping produce a clear PDF-export
error. CSV and JSON preserve their original names independently of PDF support.
