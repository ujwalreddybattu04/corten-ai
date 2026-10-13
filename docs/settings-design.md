# Settings review — 13 October 2026

Settings now separates Profile, Responses, Memory, Files and Data & sync into
focused panels. The page inherits Corten's dark palette and Plus Jakarta Sans
font. Navigation supports arrow keys, Home and End; all tabs reference real
panels. Narrow screens use a scrollable section bar. No theme selector, billing
controls or unsupported account-management actions were added.

Profile validates the trimmed name and distinguishes failed saves from success.
Response drafts remain available when switching panels. Custom style remains a
draft until the server acknowledges saving it. Preferences, memories and files
load independently, so a file-service failure does not block response settings;
retry preserves unsaved instructions. Mutations are serialized to prevent stale
list updates. File deletion requires confirmation, and failed deletion keeps the
file available for retry. Bulk memory deletion retains its confirmation.

Local browser review passed eight scenario groups: profile validation/save/error
recovery, response drafts and styles, memory controls, file confirmation and
recovery, partial loading failures, section and response-style keyboard navigation,
and all five sections
at five widths from 320 to 1440 pixels. These use isolated API fixtures, with no
real account edits or browser exceptions. TypeScript and scoped lint passed.
The release `a390bbb484a1a04197c4c95f2265eb1e35feca1f` passed both
[CI jobs](https://github.com/ujwalreddybattu04/corten-ai/actions/runs/38352938712)
and all eleven isolated storage/account safeguards during AWS deployment.
Six hosted browser scenario groups then passed using one disposable account:
real profile and preference persistence, memory add/edit/confirmed clear, upload
and download of a real CSV attachment followed by confirmed deletion, all five
sections at five viewport widths, and the concise monthly/pharma copy. No browser
exceptions occurred. The release contains only committed source and excludes
concurrent working-tree edits. The public bundle is available at
[Settings](https://d3a7ful0miola1.cloudfront.net/settings).
