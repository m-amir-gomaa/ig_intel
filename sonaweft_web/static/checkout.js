/* This page receives no PDF content or recovery key. A browser event never grants credit. */
"use strict";
const message = document.getElementById("checkout-status");
const check = document.getElementById("check-payment");
const txn = new URL(location.href).searchParams.get("_ptxn");
let csrf = "";
function showPaymentStatus(result) {
  const notices = {
    completed:
      "Payment verified. Your workspace balance reflects this purchase.",
    refunded:
      "This payment was refunded or reversed. Its processing credit has been removed.",
    partially_refunded:
      "This payment was partly refunded. Your workspace balance reflects the adjustment.",
    canceled: "This checkout was cancelled. It did not add processing credit.",
  };
  message.textContent =
    notices[result.status] ||
    "Payment is still processing or has not been completed. You can return later and check again. Do not pay again to refresh the balance.";
  const finished = Object.hasOwn(notices, result.status);
  check.hidden = finished;
  return finished;
}
async function responseJSON(response) {
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      result.detail || "Payment status is unavailable. Retry shortly.",
    );
  return result;
}
async function paymentStatus() {
  check.disabled = true;
  try {
    const result = await responseJSON(
      await fetch("/api/payment-status", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ transaction_id: txn }),
      }),
    );
    showPaymentStatus(result);
  } catch (error) {
    message.textContent = error.message;
  } finally {
    check.disabled = false;
  }
}
check.addEventListener("click", paymentStatus);
async function start() {
  try {
    if (!/^txn_[a-z0-9]{26}$/.test(txn || ""))
      throw new Error(
        "Choose a processing pack in your workspace to start checkout.",
      );
    const config = await responseJSON(
      await fetch("/api/checkout-config", { credentials: "same-origin" }),
    );
    if (!config.enabled)
      throw new Error(
        "Checkout is not open yet. Your existing workspace and sample remain available.",
      );
    const session = await responseJSON(
      await fetch("/api/session", { credentials: "same-origin" }),
    );
    csrf = session.csrf;
    // Verify server ownership before showing a payment dialog on this device.
    const initial = await responseJSON(
      await fetch("/api/payment-status", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ transaction_id: txn }),
      }),
    );
    if (showPaymentStatus(initial)) return;
    check.hidden = false;
    if (!window.Paddle)
      throw new Error(
        "Secure checkout could not load. Refresh this page or contact support.",
      );
    if (config.environment === "sandbox") Paddle.Environment.set("sandbox");
    Paddle.Initialize({
      token: config.client_token,
      eventCallback(event) {
        if (event.name === "checkout.completed") {
          message.textContent =
            "Payment received by checkout. Waiting for server verification…";
          paymentStatus();
        } else if (event.name === "checkout.closed") {
          message.textContent =
            "Checkout closed. Check payment status before starting another payment.";
        } else if (event.name === "checkout.error") {
          message.textContent =
            "Checkout encountered a problem. No credits are added without server verification.";
        }
      },
    });
    Paddle.Checkout.open({
      transactionId: txn,
      settings: {
        displayMode: "overlay",
        allowLogout: false,
        showAddDiscounts: false,
        allowDiscountRemoval: false,
      },
    });
    message.textContent =
      "Complete the secure payment dialog. Save your Sonaweft recovery key to retain access.";
  } catch (error) {
    message.textContent = error.message;
  }
}
start();
