function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function formatInline(line) {
  return line
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\((\/[^)\s]+)\)/g, (_match, label, href) => {
      // Only same-origin API paths reach here (the text is HTML-escaped
      // above, and Auralys only ever emits links to its own /reports
      // download route) -- report-download links get a marker class so the
      // chat view can intercept the click and fetch with an auth header
      // instead of a bare navigation, which would 401.
      const isDownload = href.startsWith("/reports/download/");
      const className = isDownload ? ' class="chat-download-link"' : "";
      return `<a href="${href}"${className} target="_blank" rel="noopener">${label}</a>`;
    });
}

// Renders the small subset of markdown Auralys's LLM answers actually use
// (bold labels, bullet lists) into safe HTML. Input is HTML-escaped first,
// so only the tags this function generates can ever reach the DOM.
export function formatMessage(rawText) {
  const escaped = escapeHtml(rawText);
  const lines = escaped.split(/\r?\n/);
  const blocks = [];
  let listItems = [];

  function flushList() {
    if (listItems.length) {
      blocks.push(`<ul>${listItems.map((item) => `<li>${item}</li>`).join("")}</ul>`);
      listItems = [];
    }
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    const bulletMatch = line.match(/^[*-]\s+(.*)$/);
    if (bulletMatch) {
      listItems.push(formatInline(bulletMatch[1]));
      continue;
    }
    flushList();
    if (line) {
      blocks.push(`<p>${formatInline(line)}</p>`);
    }
  }
  flushList();

  return blocks.join("") || "<p></p>";
}
