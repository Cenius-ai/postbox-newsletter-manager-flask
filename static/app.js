/* Progressive enhancement for Postbox: password reveal, demo sign-in, copy
   buttons, the Markdown preview toggle, inline validation and submit guards.
   Every form and every link works without this file; nothing here is required
   to render a page. */
(function () {
  "use strict";

  function onReady(callback) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback);
    } else {
      callback();
    }
  }

  function initPasswordToggles() {
    document.querySelectorAll("[data-password-toggle]").forEach(function (button) {
      var input = document.getElementById(button.getAttribute("data-password-toggle"));
      if (!input) {
        return;
      }
      button.addEventListener("click", function () {
        var reveal = input.type === "password";
        input.type = reveal ? "text" : "password";
        button.setAttribute("aria-pressed", reveal ? "true" : "false");
        button.textContent = reveal ? "Hide" : "Show";
      });
    });
  }

  function initDemoFill() {
    document.querySelectorAll("[data-demo-fill]").forEach(function (button) {
      button.addEventListener("click", function () {
        var form = button.closest("form") || document.querySelector("form");
        var email = document.getElementById("email");
        var password = document.getElementById("password");
        if (!form || !email || !password) {
          return;
        }
        email.value = button.getAttribute("data-email") || "";
        password.value = button.getAttribute("data-password") || "";
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          form.submit();
        }
      });
    });
  }

  function copyText(value) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(value);
    }
    return Promise.reject(new Error("Clipboard API unavailable"));
  }

  function selectAndCopy(input) {
    var copied = false;
    try {
      input.focus();
      input.select();
      copied = document.execCommand("copy");
    } catch (error) {
      copied = false;
    }
    return copied;
  }

  function announce(button, label) {
    if (!button.hasAttribute("data-original-label")) {
      button.setAttribute("data-original-label", button.textContent);
    }
    button.textContent = label;
    window.setTimeout(function () {
      button.textContent = button.getAttribute("data-original-label");
    }, 1600);
  }

  function initCopyButtons() {
    document.querySelectorAll("[data-copy]").forEach(function (button) {
      button.addEventListener("click", function () {
        var target = document.getElementById(button.getAttribute("data-copy-target"));
        if (!target) {
          return;
        }
        var value = typeof target.value === "string" ? target.value : target.textContent;
        copyText(value)
          .then(function () {
            announce(button, "Copied");
          })
          .catch(function () {
            announce(button, selectAndCopy(target) ? "Copied" : "Select and copy");
          });
      });
    });
  }

  function initComposer() {
    var textarea = document.getElementById("body_markdown");
    var preview = document.getElementById("md-preview");
    var raw = document.getElementById("md-raw");
    if (!textarea || !preview || !window.PostboxMarkdown) {
      return;
    }

    function paint() {
      window.PostboxMarkdown.render(textarea.value, preview);
      if (raw) {
        raw.textContent = textarea.value;
      }
    }

    paint();

    var timer = null;
    textarea.addEventListener("input", function () {
      if (timer) {
        window.clearTimeout(timer);
      }
      timer = window.setTimeout(paint, 80);
    });

    document.querySelectorAll("[data-md-view]").forEach(function (button) {
      button.addEventListener("click", function () {
        var mode = button.getAttribute("data-md-view");
        document.querySelectorAll("[data-md-view]").forEach(function (other) {
          var active = other === button;
          other.classList.toggle("is-active", active);
          other.setAttribute("aria-pressed", active ? "true" : "false");
        });
        preview.hidden = mode !== "preview";
        if (raw) {
          raw.hidden = mode !== "raw";
          if (mode === "raw") {
            raw.textContent = textarea.value;
          }
        }
      });
    });
  }

  function setFieldError(input, message) {
    var field = input.closest(".field");
    if (!field) {
      return;
    }
    var errorId = (input.id || input.name) + "-error";
    var error = field.querySelector(".field__error");

    if (!message) {
      field.classList.remove("field--invalid");
      input.removeAttribute("aria-invalid");
      if (error) {
        error.hidden = true;
        error.textContent = "";
      }
      return;
    }

    field.classList.add("field--invalid");
    input.setAttribute("aria-invalid", "true");
    if (!error) {
      error = document.createElement("p");
      error.className = "field__error";
      error.id = errorId;
      field.appendChild(error);
    }
    error.hidden = false;
    error.textContent = message;
    input.setAttribute("aria-describedby", errorId);
  }

  function validateForm(form) {
    var firstInvalid = null;

    form.querySelectorAll("[required]").forEach(function (input) {
      if (input.disabled || input.type === "hidden") {
        return;
      }
      var value = (input.value || "").trim();
      var message = "";

      if (input.type === "checkbox") {
        if (!input.checked) {
          message = "Tick this to continue.";
        }
      } else if (!value) {
        message = input.tagName === "SELECT" ? "Choose an option to continue." : "This field is required.";
      } else if (input.type === "email" && !/^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$/.test(value)) {
        message = "Enter a valid email address, like reader@example.com.";
      }

      setFieldError(input, message);
      if (message && !firstInvalid) {
        firstInvalid = input;
      }
    });

    if (firstInvalid) {
      firstInvalid.focus();
      return false;
    }
    return true;
  }

  function initFormGuards() {
    document.querySelectorAll("form[data-guard], form[data-validate]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (form.getAttribute("data-submitting") === "true") {
          event.preventDefault();
          return;
        }

        if (form.hasAttribute("data-validate") && !validateForm(form)) {
          event.preventDefault();
          return;
        }

        var confirmMessage = form.getAttribute("data-confirm");
        if (confirmMessage && !window.confirm(confirmMessage)) {
          event.preventDefault();
          return;
        }

        form.setAttribute("data-submitting", "true");
        var busyLabel = form.getAttribute("data-busy-label");
        var submitButton = form.querySelector('button[type="submit"]');
        if (submitButton && busyLabel) {
          submitButton.textContent = busyLabel;
        }
        if (submitButton) {
          window.setTimeout(function () {
            submitButton.disabled = true;
          }, 0);
        }
      });
    });
  }

  onReady(function () {
    initPasswordToggles();
    initDemoFill();
    initCopyButtons();
    initComposer();
    initFormGuards();
  });
})();
