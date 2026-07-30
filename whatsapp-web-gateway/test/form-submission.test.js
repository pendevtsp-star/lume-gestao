import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";


test("preserves the clicked submit action before disabling buttons", async () => {
  const source = await readFile(
    new URL("../../static/js/app.js", import.meta.url),
    "utf8"
  );
  const listeners = {};
  const appendedFields = [];
  const buttonAttributes = {};
  const button = {
    name: "action",
    value: "disconnect",
    disabled: false,
    textContent: "Desconectar WhatsApp",
    dataset: {},
    setAttribute(name, value) {
      buttonAttributes[name] = value;
    }
  };
  const form = {
    dataset: {},
    classList: { add() {} },
    appendChild(field) {
      appendedFields.push(field);
    },
    addEventListener(name, callback) {
      listeners[name] = callback;
    },
    querySelectorAll(selector) {
      return selector === "button[type='submit']" ? [button] : [];
    }
  };
  const document = {
    createElement() {
      return { dataset: {} };
    },
    querySelectorAll(selector) {
      return selector === "form:not([method='get'])" ? [form] : [];
    }
  };
  const context = {
    document,
    window: {
      addEventListener() {},
      location: { pathname: "/", search: "" },
      sessionStorage: {
        getItem() { return null; },
        removeItem() {},
        setItem() {}
      }
    }
  };

  vm.runInNewContext(source, context);

  let firstPrevented = false;
  listeners.submit({
    submitter: button,
    preventDefault() {
      firstPrevented = true;
    }
  });

  assert.equal(firstPrevented, false);
  assert.equal(appendedFields.length, 1);
  assert.equal(appendedFields[0].type, "hidden");
  assert.equal(appendedFields[0].name, "action");
  assert.equal(appendedFields[0].value, "disconnect");
  assert.equal(button.disabled, false);
  assert.equal(buttonAttributes["aria-disabled"], "true");

  let duplicatePrevented = false;
  listeners.submit({
    submitter: button,
    preventDefault() {
      duplicatePrevented = true;
    }
  });
  assert.equal(duplicatePrevented, true);
});
