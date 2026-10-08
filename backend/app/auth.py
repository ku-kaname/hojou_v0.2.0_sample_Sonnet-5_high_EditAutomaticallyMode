"""
認証・認可共通処理

【概要】
JWT認証・パスワードハッシュ・ロール判定等、認証・認可に関する共通処理を提供する
"""

import datetime as dt
import os

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.models import User

JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
JWT_ALGORITHM = os.environ["JWT_ALGORITHM"]
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"])

_password_hash = PasswordHash.recommended()
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# ====================================================================================================
# パスワードハッシュ処理
# - hash_password : パスワードハッシュ化
# - verify_password : パスワード検証

# 設計書：
# - 設計書/認証・認可（auth）/パスワードハッシュ化_v0.2.0.md
# - 設計書/認証・認可（auth）/パスワード検証_v0.2.0.md
# ====================================================================================================


def hash_password(plain_password: str) -> str:
    """
    パスワードハッシュ化

    設計書：設計書/認証・認可（auth）/パスワードハッシュ化_v0.2.0.md

    【処理概要】
    - 平文パスワードをArgon2idアルゴリズムでハッシュ化する

    【パラメータ】
    - plain_password (str) : 平文パスワード (必須)

    【戻り値】
    - hashed_password (str) : ハッシュ済みパスワード

    【例外処理】
    - なし

    【処理フロー】
    1. パスワードのハッシュ化
    2. 戻り値を返却
    """

    # 1. パスワードのハッシュ化
    hashed_password = _password_hash.hash(plain_password)

    # 2. 戻り値を返却
    return hashed_password


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    パスワード検証

    設計書：設計書/認証・認可（auth）/パスワード検証_v0.2.0.md

    【処理概要】
    - 平文パスワードが、登録済みのハッシュ済みパスワードと一致するかを検証する

    【パラメータ】
    - plain_password (str) : 平文パスワード (必須)
    - hashed_password (str) : ハッシュ済みパスワード (必須)

    【戻り値】
    - is_valid (bool) : 照合結果（一致：true／不一致：false）

    【例外処理】
    - なし

    【処理フロー】
    1. パスワードの照合
    2. 戻り値を返却
    """

    # 1. パスワードの照合
    is_valid = _password_hash.verify(plain_password, hashed_password)

    # 2. 戻り値を返却
    return is_valid


# ====================================================================================================
# アクセストークン発行
# - create_access_token : トークン発行

# 設計書：設計書/認証・認可（auth）/トークン発行_v0.3.0.md
# ====================================================================================================


def create_access_token(user_id: str, token_generation: int) -> str:
    """
    トークン発行

    設計書：設計書/認証・認可（auth）/トークン発行_v0.3.0.md

    【処理概要】
    - 認証済みユーザーに対して、アクセストークン（JWT）を発行する

    【パラメータ】
    - user_id (str) : ユーザーID (必須)
    - token_generation (int) : トークン世代 (必須)

    【戻り値】
    - access_token (str) : アクセストークン

    【例外処理】
    - なし

    【処理フロー】
    1. アクセストークンの発行
    2. 戻り値を返却
    """

    # 1. アクセストークンの発行
    expire = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "tgen": token_generation, "exp": expire}
    access_token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    # 2. 戻り値を返却
    return access_token


# ====================================================================================================
# 依存性注入（認証・認可）
# - get_current_active_user : 有効ユーザー検証
# - require_admin : 管理者権限検証
# - require_password_changed : 初回パスワード変更チェック

# 設計書：
# - 設計書/認証・認可（auth）/有効ユーザー検証_v0.2.0.md
# - 設計書/認証・認可（auth）/管理者権限検証_v0.2.0.md
# - 設計書/認証・認可（auth）/初回パスワード変更チェック_v0.2.0.md
# ====================================================================================================


def get_current_active_user(
    token: str = Depends(_oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    有効ユーザー検証

    設計書：設計書/認証・認可（auth）/有効ユーザー検証_v0.2.0.md

    【処理概要】
    - Bearerトークンを検証し、有効な登録ユーザーであることを確認する

    【パラメータ】
    - token (str) : Bearerトークン (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - current_user (User) : 登録ユーザー取得

    【例外処理】
    - HTTPException(401) : ペイロードからユーザーID・トークン世代が取得できない場合
    - HTTPException(401) : トークンが無効（署名不正・期限切れ）な場合
    - HTTPException(401) : ユーザー情報が取得できない場合
    - HTTPException(401) : 有効フラグがfalseの場合
    - HTTPException(401) : トークン世代が不一致の場合

    【処理フロー】
    1. Bearerトークンの検証
    2. 登録ユーザー取得
    3. 有効性の確認
    4. 戻り値を返却
    """

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="資格情報を検証できませんでした",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Bearerトークンの検証
    # 1.(1) トークンをデコードする
    # 1.(2) 例外処理：トークンが無効（署名不正・期限切れ）
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise credentials_exception from exc

    # 1.(2) トークンのユーザーID・トークン世代を取得
    # 1.(2).① 例外処理：ペイロードからユーザーID・トークン世代が取得できない
    user_id = payload.get("sub")
    token_generation = payload.get("tgen")
    if user_id is None or token_generation is None:
        raise credentials_exception

    # 2. 登録ユーザー取得
    # 2.(1) ユーザー情報をDBから取得する
    current_user = crud.get_user_by_user_id(db, user_id)

    # 2.(2) 例外処理：ユーザー情報が取得できない
    if current_user is None:
        raise credentials_exception

    # 3. 有効性の確認
    # 3.(1).① 例外処理：有効フラグがfalse
    if not current_user.active_flag:
        raise credentials_exception

    # 3.(1).② 例外処理：トークン世代が不一致
    if current_user.token_generation != token_generation:
        raise credentials_exception

    # 4. 戻り値を返却
    return current_user


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """
    管理者権限検証

    設計書：設計書/認証・認可（auth）/管理者権限検証_v0.2.0.md

    【処理概要】
    - リクエストを行ったユーザーが、管理者ロールであることを確認する

    【パラメータ】
    - current_user (User) : 登録ユーザー取得 (必須)

    【戻り値】
    - current_admin (User) : 登録ユーザー取得

    【例外処理】
    - HTTPException(403) : ロールが"管理者"でない場合

    【処理フロー】
    1. 管理者ロールの確認
    2. 戻り値を返却
    """

    # 1. 管理者ロールの確認
    # 1.① 例外処理：ロールが"管理者"でない
    if current_user.role != "管理者":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="この操作には管理者権限が必要です。",
        )

    # 2. 戻り値を返却
    return current_user


def require_password_changed(current_user: User = Depends(get_current_active_user)) -> User:
    """
    初回パスワード変更チェック

    設計書：設計書/認証・認可（auth）/初回パスワード変更チェック_v0.2.0.md

    【処理概要】
    - 初回パスワード変更が完了していないユーザーによる、パスワード変更・ログアウト以外の操作を拒否する

    【パラメータ】
    - current_user (User) : 登録ユーザー取得 (必須)

    【戻り値】
    - current_user (User) : 登録ユーザー取得

    【例外処理】
    - HTTPException(403) : 初回パスワード変更要否フラグが変更要の場合

    【処理フロー】
    1. 初回パスワード変更要否フラグの確認
    2. 戻り値を返却
    """

    # 1. 初回パスワード変更要否フラグの確認
    # 1.① 例外処理：変更要
    if current_user.password_change_required_flag:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="初回パスワード変更が完了していません。パスワードを変更してください。",
        )

    # 2. 戻り値を返却
    return current_user
