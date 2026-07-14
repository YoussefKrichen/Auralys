function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function formatInline(line) {
  return line
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
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
