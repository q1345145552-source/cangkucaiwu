"use client";
import { useEffect } from "react";

const overlays = '.modal-overlay, [data-modal-overlay="true"]';
const fields = 'input:not([type="hidden"]):not([type="submit"]):not([type="button"]), textarea, select, [contenteditable="true"]';
function value(element: Element): string {
  if (element instanceof HTMLInputElement) {
    if (element.type === 'file') return Array.from(element.files || []).map(f => `${f.name}:${f.size}:${f.lastModified}`).join('|');
    if (['checkbox', 'radio'].includes(element.type)) return String(element.checked);
  }
  if (element instanceof HTMLSelectElement) return Array.from(element.selectedOptions).map(o => o.value).join('|');
  return element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement ? element.value : element.textContent || '';
}
/** Only explicit close buttons dismiss dialogs. Dirty checks never intercept save/submit. */
export default function ModalCloseGuard() {
  useEffect(() => {
    const initial = new WeakMap<Element, string>(), edited = new WeakSet<Element>();
    const touched = new WeakMap<Element, Set<Element>>();
    function register() {
      document.querySelectorAll(overlays).forEach(overlay => overlay.querySelectorAll(fields).forEach(field => {
        // Async initial data may replace an untouched value; it is not a user edit.
        if (!edited.has(field)) initial.set(field, value(field));
      }));
    }
    register();
    const observer = new MutationObserver(register);
    observer.observe(document.body, { childList: true, subtree: true });
    function focus(event: Event) {
      const field = event.target;
      if (field instanceof Element && field.matches(fields) && field.closest(overlays) && !edited.has(field)) initial.set(field, value(field));
    }
    function change(event: Event) {
      const field = event.target;
      if (field instanceof Element && field.matches(fields)) {
        const overlay=field.closest(overlays);
        if (overlay) { edited.add(field); const set=touched.get(overlay)||new Set<Element>();set.add(field);touched.set(overlay,set); }
      }
    }
    function click(event: MouseEvent) {
      const target = event.target instanceof Element ? event.target : null;
      const button = target?.closest('button, [role="button"]'), overlay = button?.closest(overlays);
      if (!button || !overlay || button.hasAttribute('disabled')) return;
      const label = (button.getAttribute('aria-label') || button.textContent || '').trim();
      const close = button.hasAttribute('data-modal-close') || /^(关闭(?:图片预览)?|取消|返回|放弃|×|✕|✖|X|close|cancel)$/i.test(label) || !!button.querySelector('.lucide-x');
      if (!close) {
        // Plus/minus, autocomplete and row controls can update controlled fields without
        // emitting native input/change events. Compare only existing fields after React flushes.
        const before = new Map(Array.from(overlay.querySelectorAll(fields)).filter(f=>f.closest(overlays)===overlay).map(f=>[f,value(f)]));
        const explicitEdit=button.hasAttribute('data-modal-edit');
        setTimeout(() => {
          if (!overlay.isConnected) return;
          const set=touched.get(overlay)||new Set<Element>();
          before.forEach((previous,field)=>{
            if (!overlay.contains(field) || value(field)!==previous) {
              if (!edited.has(field)) initial.set(field,previous);
              edited.add(field);set.add(field);
            }
          });
          if(explicitEdit){
            // An added row/selected item is an unsaved edit even before typing into it.
            edited.add(button);initial.set(button,'unselected');set.add(button);
          }
          touched.set(overlay,set);
        },0);
        return;
      }
      const dirty = Array.from(touched.get(overlay)||[]).some(field => !overlay.contains(field) || initial.get(field) !== value(field));
      if (dirty && !window.confirm('已填内容将丢失，确定关闭吗？')) {
        event.preventDefault(); event.stopImmediatePropagation();
      }
    }
    // Existing per-page Escape handlers must not bypass explicit close/dirty checks.
    function key(event: KeyboardEvent) {
      if (event.key === 'Escape' && document.querySelector(overlays)) { event.preventDefault(); event.stopImmediatePropagation(); }
    }
    document.addEventListener('focusin', focus, true);
    document.addEventListener('input', change, true);
    document.addEventListener('change', change, true);
    document.addEventListener('click', click, true);
    document.addEventListener('keydown', key, true);
    return () => {
      observer.disconnect();
      document.removeEventListener('focusin', focus, true);
      document.removeEventListener('input', change, true);
      document.removeEventListener('change', change, true);
      document.removeEventListener('click', click, true);
      document.removeEventListener('keydown', key, true);
    };
  }, []);
  return null;
}
