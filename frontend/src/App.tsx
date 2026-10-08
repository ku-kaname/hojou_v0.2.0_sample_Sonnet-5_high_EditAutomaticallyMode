/**
 * ルーティング定義
 *
 * 【概要】
 * 認証コンテキストの提供、およびロール別ガードを用いたルーティングの骨格を提供する
 * 画面単位のルート（S01〜S11）は、各対応する機能群の実装バックログで本ファイルへ追記する
 */

import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* 画面単位のルートは、各対応する機能群の実装バックログで本ファイルへ追記する */}
          <Route path="*" element={<p>準備中です。</p>} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
