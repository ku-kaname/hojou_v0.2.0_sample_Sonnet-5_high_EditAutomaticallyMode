"""
API入出力DTO

【概要】
リクエスト・レスポンスのスキーマ定義（Pydantic）を提供する
"""

import datetime as dt

from pydantic import BaseModel, Field

# ====================================================================================================
# 認証・認可
# - TokenResponse : トークンレスポンス

# 設計書：設計書/スキーマ（schemas）/認証・認可_v0.3.0.md
# ====================================================================================================


class TokenResponse(BaseModel):
    """
    トークンレスポンス

    設計書：設計書/スキーマ（schemas）/認証・認可_v0.3.0.md
    """

    access_token: str
    token_type: str
    password_change_required: bool


# ====================================================================================================
# ユーザー操作
# - UserBase : ユーザー基本情報
# - UserCreateRequest : ユーザー作成リクエスト
# - UserCreateResponse : ユーザー作成レスポンス
# - UserUpdateRequest : ユーザー更新リクエスト
# - UserUpdateResponse : ユーザー更新レスポンス
# - UserGetResponse : ユーザー取得レスポンス
# - PasswordChangeRequest : パスワード変更リクエスト
# - PasswordResetRequest : パスワード初期化リクエスト

# 設計書：設計書/スキーマ（schemas）/ユーザー操作_v0.2.0.md
# ====================================================================================================


class UserBase(BaseModel):
    """
    ユーザー基本情報

    設計書：設計書/スキーマ（schemas）/ユーザー操作_v0.2.0.md
    """

    name: str = Field(min_length=1, max_length=50)
    department: str = Field(default="", max_length=50)


class UserCreateRequest(UserBase):
    """
    ユーザー作成リクエスト

    設計書：設計書/スキーマ（schemas）/ユーザー操作_v0.2.0.md
    """

    user_id: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    role: str
    initial_password: str = Field(min_length=8, max_length=32)


class UserCreateResponse(UserBase):
    """
    ユーザー作成レスポンス

    設計書：設計書/スキーマ（schemas）/ユーザー操作_v0.2.0.md
    """

    user_id: str
    role: str
    active_flag: bool
    password_change_required_flag: bool
    created_at: dt.datetime


class UserUpdateRequest(UserBase):
    """
    ユーザー更新リクエスト

    設計書：設計書/スキーマ（schemas）/ユーザー操作_v0.2.0.md
    """

    role: str


class UserUpdateResponse(UserBase):
    """
    ユーザー更新レスポンス

    設計書：設計書/スキーマ（schemas）/ユーザー操作_v0.2.0.md
    """

    user_id: str
    role: str
    active_flag: bool
    password_change_required_flag: bool
    updated_at: dt.datetime


class UserGetResponse(UserBase):
    """
    ユーザー取得レスポンス

    設計書：設計書/スキーマ（schemas）/ユーザー操作_v0.2.0.md
    """

    user_id: str
    role: str
    active_flag: bool
    password_change_required_flag: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class PasswordChangeRequest(BaseModel):
    """
    パスワード変更リクエスト

    設計書：設計書/スキーマ（schemas）/ユーザー操作_v0.2.0.md
    """

    current_password: str = Field(min_length=8, max_length=32)
    new_password: str = Field(min_length=8, max_length=32)


class PasswordResetRequest(BaseModel):
    """
    パスワード初期化リクエスト

    設計書：設計書/スキーマ（schemas）/ユーザー操作_v0.2.0.md
    """

    initial_password: str = Field(min_length=8, max_length=32)


# ====================================================================================================
# 備品操作
# - EquipmentBase : 備品ベース
# - EquipmentCreateRequest : 備品登録リクエスト
# - EquipmentResponse : 備品レスポンス
# - EquipmentUpdateRequest : 備品編集リクエスト
# - ReservationResponse : 予約情報

# 設計書：設計書/スキーマ（schemas）/備品操作_v0.2.0.md
# ====================================================================================================


class EquipmentBase(BaseModel):
    """
    備品ベース

    設計書：設計書/スキーマ（schemas）/備品操作_v0.2.0.md
    """

    asset_number: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9-]+$")
    name: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=50)
    description: str = Field(default="", max_length=500)
    location: str = Field(default="", max_length=100)


class EquipmentCreateRequest(EquipmentBase):
    """
    備品登録リクエスト

    設計書：設計書/スキーマ（schemas）/備品操作_v0.2.0.md
    """


class EquipmentResponse(EquipmentBase):
    """
    備品レスポンス

    設計書：設計書/スキーマ（schemas）/備品操作_v0.2.0.md
    """

    equipment_id: int
    active_flag: bool
    loan_status: str
    due_date: dt.date | None
    created_at: dt.datetime
    updated_at: dt.datetime


class EquipmentUpdateRequest(EquipmentBase):
    """
    備品編集リクエスト

    設計書：設計書/スキーマ（schemas）/備品操作_v0.2.0.md
    """


class ReservationResponse(BaseModel):
    """
    予約情報

    設計書：設計書/スキーマ（schemas）/備品操作_v0.2.0.md
    """

    loan_request_id: int
    start_date: dt.date
    due_date: dt.date
    status: str
    applicant_name: str | None = None


# ====================================================================================================
# 備品CSV一括登録
# - EquipmentBulkImportErrorDetail : 備品CSV一括登録エラー詳細
# - EquipmentBulkImportErrorResponse : 備品CSV一括登録エラーレスポンス
# - EquipmentBulkImportResponse : 備品CSV一括登録レスポンス

# 設計書：設計書/スキーマ（schemas）/備品CSV一括登録_v0.2.0.md
# ====================================================================================================


class EquipmentBulkImportErrorDetail(BaseModel):
    """
    備品CSV一括登録エラー詳細

    設計書：設計書/スキーマ（schemas）/備品CSV一括登録_v0.2.0.md
    """

    row_number: int | None
    message: str


class EquipmentBulkImportErrorResponse(BaseModel):
    """
    備品CSV一括登録エラーレスポンス

    設計書：設計書/スキーマ（schemas）/備品CSV一括登録_v0.2.0.md
    """

    error_list: list[EquipmentBulkImportErrorDetail]


class EquipmentBulkImportResponse(BaseModel):
    """
    備品CSV一括登録レスポンス

    設計書：設計書/スキーマ（schemas）/備品CSV一括登録_v0.2.0.md
    """

    registered_count: int
    equipment_list: list[EquipmentResponse]


# ====================================================================================================
# 貸出申請操作
# - LoanRequestBase : 貸出申請ベース
# - LoanRequestCreateRequest : 貸出申請登録リクエスト
# - LoanRequestResponse : 貸出申請レスポンス
# - LoanRequestCancelRequest : 貸出申請取消リクエスト
# - LoanRequestRejectRequest : 貸出申請却下リクエスト
# - LoanRequestAdminCancelRequest : 貸出申請管理者取消リクエスト

# 設計書：設計書/スキーマ（schemas）/貸出申請操作_v0.3.0.md
# ====================================================================================================


class LoanRequestBase(BaseModel):
    """
    貸出申請ベース

    設計書：設計書/スキーマ（schemas）/貸出申請操作_v0.3.0.md
    """

    equipment_id: int
    start_date: dt.date
    due_date: dt.date
    purpose: str = Field(min_length=1, max_length=200)


class LoanRequestCreateRequest(LoanRequestBase):
    """
    貸出申請登録リクエスト

    設計書：設計書/スキーマ（schemas）/貸出申請操作_v0.3.0.md
    """


class LoanRequestResponse(LoanRequestBase):
    """
    貸出申請レスポンス

    設計書：設計書/スキーマ（schemas）/貸出申請操作_v0.3.0.md
    """

    loan_request_id: int
    applicant_user_id: int
    status: str
    reject_cancel_reason: str | None
    approved_rejected_by_user_id: int | None
    lent_by_user_id: int | None
    returned_by_user_id: int | None
    cancelled_by_user_id: int | None
    requested_at: dt.datetime
    approved_rejected_at: dt.datetime | None
    lent_at: dt.datetime | None
    returned_at: dt.datetime | None
    cancelled_at: dt.datetime | None
    return_note: str | None


class LoanRequestCancelRequest(BaseModel):
    """
    貸出申請取消リクエスト

    設計書：設計書/スキーマ（schemas）/貸出申請操作_v0.3.0.md
    """

    reason: str | None = Field(default=None, max_length=200)


class LoanRequestRejectRequest(BaseModel):
    """
    貸出申請却下リクエスト

    設計書：設計書/スキーマ（schemas）/貸出申請操作_v0.3.0.md
    """

    reason: str = Field(min_length=1, max_length=200)


class LoanRequestAdminCancelRequest(BaseModel):
    """
    貸出申請管理者取消リクエスト

    設計書：設計書/スキーマ（schemas）/貸出申請操作_v0.3.0.md
    """

    reason: str = Field(min_length=1, max_length=200)


# ====================================================================================================
# 通知操作
# - NotificationResponse : 通知レスポンス

# 設計書：設計書/スキーマ（schemas）/通知操作_v0.2.0.md
# ====================================================================================================


class NotificationResponse(BaseModel):
    """
    通知レスポンス

    設計書：設計書/スキーマ（schemas）/通知操作_v0.2.0.md
    """

    notification_id: int
    notification_type: str
    loan_request_id: int
    read_flag: bool
    created_at: dt.datetime
