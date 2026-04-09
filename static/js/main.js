// Auto-dismiss flash messages after 4 seconds
document.addEventListener("DOMContentLoaded", function () {
  const flashes = document.querySelectorAll(".flash");
  flashes.forEach(function (el) {
    setTimeout(function () {
      el.style.transition = "opacity 0.5s ease";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 500);
    }, 4000);
  });

  // Set today's date as default for date inputs
  const dateInputs = document.querySelectorAll("input[type='date']");
  dateInputs.forEach(function (input) {
    if (!input.value) {
      const today = new Date().toISOString().split("T")[0];
      input.value = today;
    }
  });
});
