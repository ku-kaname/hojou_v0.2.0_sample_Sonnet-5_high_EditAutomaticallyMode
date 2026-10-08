/**
 * 共通レイアウト
 *
 * 【概要】
 * ヘッダーと画面本体を組み合わせる共通の画面枠を提供する
 * 画面間の遷移リンク（ナビゲーション）は、各画面の実装バックログでヘッダー内に追記する
 */

import type { ReactNode } from "react";
import { Header } from "./Header";

export function Layout({ children }: { children: ReactNode }) {
  return (
    <>
      <Header />
      <main>{children}</main>
    </>
  );
}
