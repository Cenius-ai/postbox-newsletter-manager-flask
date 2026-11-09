/* Client-side Markdown preview for the campaign composer.
   Mirrors the subset rendered server-side by app/markdown_render.py, but builds
   DOM nodes directly so every piece of user text goes through textContent —
   a campaign body can never inject markup. */
(function () {
  "use strict";

  var SAFE_URL = /^(https?:\/\/|mailto:|\/|#)/i;
  var INLINE_SOURCE = "(`[^`\\n]+`)|(\\*\\*[^*\\n]+\\*\\*)|(\\*[^*\\n]+\\*)|(\\[[^\\]\\n]+\\]\\([^)\\s]+\\))";

  function inline(text, parent) {
    var pattern = new RegExp(INLINE_SOURCE, "g");
    var lastIndex = 0;
    var match;

    while ((match = pattern.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parent.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
      }
      var token = match[0];

      if (token.charAt(0) === "`") {
        var code = document.createElement("code");
        code.textContent = token.slice(1, -1);
        parent.appendChild(code);
      } else if (token.slice(0, 2) === "**") {
        var strong = document.createElement("strong");
        inline(token.slice(2, -2), strong);
        parent.appendChild(strong);
      } else if (token.charAt(0) === "*") {
        var em = document.createElement("em");
        inline(token.slice(1, -1), em);
        parent.appendChild(em);
      } else {
        var split = token.indexOf("](");
        var label = token.slice(1, split);
        var href = token.slice(split + 2, -1);
        if (SAFE_URL.test(href)) {
          var anchor = document.createElement("a");
          anchor.setAttribute("href", href);
          anchor.setAttribute("rel", "noopener noreferrer nofollow");
          inline(label, anchor);
          parent.appendChild(anchor);
        } else {
          parent.appendChild(document.createTextNode(label));
        }
      }
      lastIndex = match.index + token.length;
    }

    if (lastIndex < text.length) {
      parent.appendChild(document.createTextNode(text.slice(lastIndex)));
    }
  }

  function isBullet(line) {
    return /^\s*[-*+]\s+/.test(line);
  }

  function isOrdered(line) {
    return /^\s*\d+[.)]\s+/.test(line);
  }

  function render(text, target) {
    target.textContent = "";

    var lines = String(text || "").replace(/\r\n?/g, "\n").split("\n");
    var paragraph = [];
    var index = 0;

    function flushParagraph() {
      if (!paragraph.length) {
        return;
      }
      var element = document.createElement("p");
      paragraph.forEach(function (line, position) {
        if (position) {
          element.appendChild(document.createElement("br"));
        }
        inline(line, element);
      });
      target.appendChild(element);
      paragraph = [];
    }

    while (index < lines.length) {
      var raw = lines[index];
      var line = raw.trim();

      if (line.indexOf("```") === 0) {
        flushParagraph();
        index += 1;
        var codeLines = [];
        while (index < lines.length && lines[index].trim().indexOf("```") !== 0) {
          codeLines.push(lines[index]);
          index += 1;
        }
        index += 1;
        var pre = document.createElement("pre");
        var codeElement = document.createElement("code");
        codeElement.textContent = codeLines.join("\n");
        pre.appendChild(codeElement);
        target.appendChild(pre);
        continue;
      }

      if (!line) {
        flushParagraph();
        index += 1;
        continue;
      }

      var heading = /^(#{1,6})\s+(.*)$/.exec(line);
      if (heading) {
        flushParagraph();
        var level = Math.min(6, 1 + heading[1].length);
        var headingElement = document.createElement("h" + level);
        inline(heading[2], headingElement);
        target.appendChild(headingElement);
        index += 1;
        continue;
      }

      if (/^(---+|\*\*\*+|___+)$/.test(line)) {
        flushParagraph();
        target.appendChild(document.createElement("hr"));
        index += 1;
        continue;
      }

      if (line.charAt(0) === ">") {
        flushParagraph();
        var quoted = [];
        while (index < lines.length && lines[index].trim().charAt(0) === ">") {
          quoted.push(lines[index].trim().replace(/^>\s?/, ""));
          index += 1;
        }
        var quote = document.createElement("blockquote");
        var quoteParagraph = document.createElement("p");
        quoted.forEach(function (part, position) {
          if (position) {
            quoteParagraph.appendChild(document.createElement("br"));
          }
          inline(part, quoteParagraph);
        });
        quote.appendChild(quoteParagraph);
        target.appendChild(quote);
        continue;
      }

      if (isBullet(raw)) {
        flushParagraph();
        var list = document.createElement("ul");
        while (index < lines.length && isBullet(lines[index])) {
          var item = document.createElement("li");
          inline(lines[index].trim().replace(/^[-*+]\s+/, ""), item);
          list.appendChild(item);
          index += 1;
        }
        target.appendChild(list);
        continue;
      }

      if (isOrdered(raw)) {
        flushParagraph();
        var ordered = document.createElement("ol");
        while (index < lines.length && isOrdered(lines[index])) {
          var orderedItem = document.createElement("li");
          inline(lines[index].trim().replace(/^\d+[.)]\s+/, ""), orderedItem);
          ordered.appendChild(orderedItem);
          index += 1;
        }
        target.appendChild(ordered);
        continue;
      }

      paragraph.push(raw);
      index += 1;
    }

    flushParagraph();

    if (!target.childNodes.length) {
      var empty = document.createElement("p");
      empty.className = "preview__empty";
      empty.textContent = "Nothing written yet.";
      target.appendChild(empty);
    }
  }

  window.PostboxMarkdown = { render: render };
})();
