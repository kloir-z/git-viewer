# File Editing Design

## Overview

Add inline file editing to the Files tab. Users can edit text files directly in the browser and save changes to the working tree.

## Backend

### `PUT /api/blob`

Save file content to the working tree.

- **Request**: `PUT /api/blob` with JSON body `{"repo": "<name>", "path": "<file-path>", "content": "<text>"}`
- **Validation**:
  - `valid_repo(name)` for repo validation
  - Path traversal prevention: reject `..`, verify `resolve()` stays within repo
  - File must already exist (no new file creation)
- **Processing**: Write `content` as UTF-8 to the resolved file path
- **Response**: `{"ok": true}` on success; appropriate HTTP error on failure

## Frontend

### Edit button

- Add an "Edit" button to the section header when displaying text files
- Not shown for images, PDFs, or binary files

### Edit mode

- Clicking "Edit" replaces the highlighted code / rendered markdown with a `<textarea>`
- Textarea is pre-filled with the raw file content
- "Save" and "Cancel" buttons are shown below the textarea
- "Save" sends `PUT /api/blob`, then re-renders the file with syntax highlighting
- "Cancel" reverts to the read-only highlighted view without any API call

## Scope

- Text files only (files currently rendered with syntax highlighting or markdown)
- Existing files only (no new file creation)
- No git commit/stage functionality
- No authentication (LAN/local use only)
