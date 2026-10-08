/**
 * エントリーポイント
 *
 * 【概要】
 * Reactアプリケーションをルート要素へマウントする
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("root要素が見つかりません");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
