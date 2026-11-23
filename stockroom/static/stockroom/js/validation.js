(function () {
  function messageFor(input) {
    if (input.validity.valueMissing) return "This field is required.";
    if (input.validity.patternMismatch) {
      return input.dataset.patternMessage || "This value is not in the expected format.";
    }
    if (input.validity.rangeUnderflow) return "Enter a value of at least " + input.min + ".";
    if (input.validity.rangeOverflow) {
      return input.dataset.overflowMessage || "Enter a value no higher than " + input.max + ".";
    }
    if (input.validity.tooLong) return "Use at most " + input.maxLength + " characters.";
    if (input.validity.typeMismatch) return "Enter a valid value.";
    return "";
  }

  function matchMessage(input) {
    const otherId = input.dataset.mustMatch;
    if (!otherId) return "";
    const other = document.getElementById(otherId);
    if (!other || (!input.value && !input.required)) return "";
    if (input.value !== other.value) {
      return input.dataset.mustMatchMessage || "These values do not match.";
    }
    return "";
  }

  function errorElement(input) {
    return document.getElementById(input.id + "-error");
  }

  function crossFieldMessage(input) {
    const otherId = input.dataset.notBefore;
    if (!otherId || !input.value) return "";
    const other = document.getElementById(otherId);
    if (other && other.value && input.value < other.value) {
      return input.dataset.notBeforeMessage || "This date is too early.";
    }
    return "";
  }

  function syncConditional(form) {
    form.querySelectorAll("[data-required-when-field]").forEach(function (input) {
      const other = document.getElementById(input.dataset.requiredWhenField);
      const needed = Boolean(other && other.value === input.dataset.requiredWhenValue);
      input.required = needed;
      const mark = input.closest(".field") && input.closest(".field").querySelector(".req");
      if (mark) mark.hidden = !needed;
    });
    form.querySelectorAll("[data-required-unless-field]").forEach(function (input) {
      const other = document.getElementById(input.dataset.requiredUnlessField);
      const skip = Boolean(other && other.value === input.dataset.requiredUnlessValue);
      input.required = !skip;
      const mark = input.closest(".field") && input.closest(".field").querySelector(".req");
      if (mark) mark.hidden = skip;
    });
  }

  function validateInput(input) {
    if (input.disabled || input.type === "hidden") return true;
    syncConditional(input.form);
    const message = messageFor(input) || crossFieldMessage(input) || matchMessage(input);
    const error = errorElement(input);
    if (error && (message || input.dataset.touched === "true")) {
      error.textContent = message;
    }
    const field = input.closest(".field");
    if (field) field.classList.toggle("is-invalid", Boolean(message));
    return !message;
  }

  function focusNext(input) {
    const controls = Array.from(input.form.querySelectorAll("input, select, textarea, button")).filter(function (control) {
      return !control.disabled && control.type !== "hidden" && control.tabIndex !== -1;
    });
    const index = controls.indexOf(input);
    const next = controls[index + 1];
    if (next) next.focus();
  }

  document.querySelectorAll("form[data-validate], form[data-confirm]").forEach(function (form) {
    if (form.hasAttribute("data-validate")) form.setAttribute("novalidate", "novalidate");
    form.querySelectorAll("input, select, textarea").forEach(function (input) {
      input.addEventListener("input", function () {
        input.dataset.touched = "true";
        validateInput(input);
        form.querySelectorAll("[data-must-match]").forEach(function (other) {
          if (other.dataset.mustMatch === input.id && other.dataset.touched === "true") validateInput(other);
        });
      });
      input.addEventListener("blur", function () {
        input.dataset.touched = "true";
        validateInput(input);
      });
    });
    form.addEventListener("change", function () { syncConditional(form); });
    form.addEventListener("submit", function (event) {
      if (event.submitter && event.submitter.hasAttribute("formnovalidate")) return;
      syncConditional(form);
      let ok = true;
      let first = null;
      form.querySelectorAll("input, select, textarea").forEach(function (input) {
        input.dataset.touched = "true";
        if (!validateInput(input)) {
          ok = false;
          first = first || input;
        }
      });
      if (!ok) {
        event.preventDefault();
        if (first) first.focus();
        return;
      }
      const prompt = form.dataset.confirm;
      if (prompt && !window.confirm(prompt)) event.preventDefault();
    });
  });

  const scannerSubmits = document.body.dataset.scannerSubmit !== "false";
  document.querySelectorAll("[data-scan-mode]").forEach(function (input) {
    input.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") return;
      if (input.dataset.scanMode === "next") {
        event.preventDefault();
        focusNext(input);
      } else if (input.dataset.scanMode === "submit" && !scannerSubmits) {
        event.preventDefault();
      }
    });
  });

  document.querySelectorAll("form").forEach(function (form) { syncConditional(form); });

  document.querySelectorAll("form[data-label-action]").forEach(function (form) {
    form.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" || event.target.tagName === "TEXTAREA") return;
      if (event.target.matches("input, select")) event.preventDefault();
    });
  });
})();
