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
Hosted verification is recorded after release.
