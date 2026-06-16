/* ── SortableJS Drag-and-Drop ── */

function initSortable(container) {
  if (container.sortable) return;
  container.sortable = new Sortable(container, {
    group: "cards",
    animation: 150,
    ghostClass: "card-ghost",
    onEnd: function (evt) {
      const cardId = evt.item.dataset.cardId;
      const newListId = evt.to.dataset.listId;
      const position = (evt.newIndex + 1) * 1000;
      htmx.ajax("PATCH", "/cards/" + cardId + "/move", {
        values: { list_id: newListId, position: position },
      });
    },
  });
}

document.querySelectorAll(".cards").forEach(initSortable);

/* ── HTMX Event Handlers ── */

// After HTMX swaps new content, init Sortable on fresh .cards containers
document.body.addEventListener("htmx:afterSettle", function (evt) {
  evt.detail.target.querySelectorAll(".cards").forEach(initSortable);
});

// After any card move completes, trigger a board-wide refresh
document.body.addEventListener("htmx:afterRequest", function (evt) {
  if (evt.detail.pathInfo.requestPath.indexOf("/move") !== -1) {
    htmx.trigger("body", "boardRefresh");
  }
});

// Close modal on overlay click (not on content click)
document.addEventListener("click", function (evt) {
  var overlay = evt.target.closest(".modal-overlay");
  if (overlay && evt.target === overlay) {
    overlay.classList.remove("active");
  }
});

// Close modal on Escape key
document.addEventListener("keydown", function (evt) {
  if (evt.key === "Escape") {
    var modal = document.getElementById("modal");
    if (modal) modal.innerHTML = "";
  }
});

// Listen for boardRefresh event — triggers a full page reload
document.addEventListener("boardRefresh", function () {
  window.location.reload();
});
