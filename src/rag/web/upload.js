// Talking to the server about the visitor's own document. Messages come back as plain sentences to show on screen.

async function read(response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "Something went wrong. Please try again.";
    throw Object.assign(new Error(detail), { status: response.status });
  }
  return body;
}

async function call(path, options) {
  try {
    return await read(await fetch(path, { cache: "no-store", ...options }));
  } catch (error) {
    if (error.status) throw error;
    throw Object.assign(new Error("Couldn't reach the server. Check your connection and try again."), { status: 0 });
  }
}

/** The current state of this session's document: { state: "none" | "indexing" | "ready" | "error", ... }. */
export const getDocument = () => call("/documents");

/** Send a file. The file's bytes are the request body and its name travels in a header. */
export const sendDocument = (file) => call("/documents", {
  method: "POST",
  headers: { "X-Filename": encodeURIComponent(file.name), "Content-Type": "application/octet-stream" },
  body: file,
});

/** Remove the document, or cancel indexing it. */
export const removeDocument = () => call("/documents", { method: "DELETE" });
