"""
テーブルモデル

【概要】
設計書：テーブル定義（models）_v0.2.0.md に基づくテーブルモデル一式
"""

import datetime as dt

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """
    ユーザー情報

    【概要】
    社員アカウント（一般・管理者）を管理する

    【属性】
    - id (int): 内部ID（自動採番）
    - user_id (str): ユーザーID（半角英数字と`_`・`-`のみ。一意）
    - name (str): 氏名
    - department (str): 所属（空文字許容）
    - hashed_password (str): パスワードハッシュ（Argon2id）
    - role (str): ロール（'一般'・'管理者'。既定値："一般"）
    - active_flag (bool): 有効フラグ（既定値：true。無効化＝論理削除）
    - password_change_required_flag (bool): 初回パスワード変更要否フラグ（既定値：true）
    - token_generation (int): トークン世代（既定値：0。失効操作のたびに+1）
    - login_failure_count (int): 連続認証失敗回数（既定値：0）
    - locked_until (datetime | None): ロック解除日時（空欄許容）
    - created_at (datetime): 作成日時
    - updated_at (datetime): 更新日時
    """

    __tablename__ = "USER"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_user_id"),
        CheckConstraint("role IN ('一般', '管理者')", name="ck_user_role"),
        Index("idx_user_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    department: Mapped[str] = mapped_column(String(50), nullable=False, server_default="")
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, server_default="一般")
    active_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    password_change_required_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    token_generation: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    login_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Equipment(Base):
    """
    備品情報

    【概要】
    貸出対象の備品を個体単位で管理する

    【属性】
    - id (int): 内部ID（自動採番）
    - asset_number (str): 資産番号（半角英数字と`-`のみ。一意）
    - name (str): 備品名
    - category (str): 分類（自由入力）
    - description (str): 説明（空文字許容）
    - location (str): 保管場所（空文字許容）
    - active_flag (bool): 有効フラグ（既定値：true。無効化＝論理削除）
    - created_at (datetime): 作成日時
    - updated_at (datetime): 更新日時
    """

    __tablename__ = "EQUIPMENT"
    __table_args__ = (
        UniqueConstraint("asset_number", name="uq_equipment_asset_number"),
        Index("idx_equipment_asset_number", "asset_number"),
        Index("idx_equipment_category", "category"),
        Index("idx_equipment_active_flag", "active_flag"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_number: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, server_default="")
    location: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
    active_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class LoanRequest(Base):
    """
    貸出申請情報

    【概要】
    貸出の申請から返却までの一連の状態（貸出履歴を兼ねる）を管理する

    【属性】
    - id (int): 内部ID（自動採番）
    - equipment_id (int): 備品（内部ID）
    - applicant_user_id (int): 申請者（ユーザー内部ID）
    - start_date (date): 開始日
    - due_date (date): 返却予定日
    - purpose (str): 用途
    - status (str): 状態（'申請中'・'承認済み'・'貸出中'・'返却済み'・'却下'・'取消'。既定値："申請中"）
    - reject_cancel_reason (str): 却下・取消理由（空欄許容）
    - approved_rejected_by_user_id (int | None): 承認・却下した管理者（ユーザー内部ID。空欄許容）
    - lent_by_user_id (int | None): 貸出処理した管理者（ユーザー内部ID。空欄許容）
    - returned_by_user_id (int | None): 返却処理した管理者（ユーザー内部ID。空欄許容）
    - cancelled_by_user_id (int | None): 取消した者（ユーザー内部ID。空欄許容）
    - requested_at (datetime): 申請日時
    - approved_rejected_at (datetime | None): 承認却下日時（空欄許容）
    - lent_at (datetime | None): 貸出日時（空欄許容）
    - returned_at (datetime | None): 返却日時（空欄許容）
    - cancelled_at (datetime | None): 取消日時（空欄許容）
    - return_note (str): 返却時状態メモ（空欄許容）
    """

    __tablename__ = "LOAN_REQUEST"
    __table_args__ = (
        CheckConstraint(
            "status IN ('申請中', '承認済み', '貸出中', '返却済み', '却下', '取消')",
            name="ck_loan_request_status",
        ),
        Index("idx_loan_request_equipment_id", "equipment_id"),
        Index("idx_loan_request_applicant_user_id", "applicant_user_id"),
        Index("idx_loan_request_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("EQUIPMENT.id", name="fk_loan_request_equipment_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    applicant_user_id: Mapped[int] = mapped_column(
        ForeignKey("USER.id", name="fk_loan_request_applicant_user_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    due_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    purpose: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="申請中")
    reject_cancel_reason: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")
    approved_rejected_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("USER.id", name="fk_loan_request_approved_rejected_by", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=True,
    )
    lent_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("USER.id", name="fk_loan_request_lent_by", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=True,
    )
    returned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("USER.id", name="fk_loan_request_returned_by", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=True,
    )
    cancelled_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("USER.id", name="fk_loan_request_cancelled_by", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=True,
    )
    requested_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    approved_rejected_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    lent_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    returned_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    return_note: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")


class Notification(Base):
    """
    通知情報

    【概要】
    アプリ内通知（承認・却下・取消・新規申請・返却期限）を管理する

    【属性】
    - id (int): 内部ID（自動採番）
    - recipient_user_id (int): 宛先（ユーザー内部ID）
    - notification_type (str): 種別（'承認'・'却下'・'取消'・'新規申請'・'返却期限'）
    - loan_request_id (int): 関連申請（内部ID）
    - read_flag (bool): 既読フラグ（既定値：false）
    - created_at (datetime): 作成日時
    """

    __tablename__ = "NOTIFICATION"
    __table_args__ = (
        CheckConstraint(
            "notification_type IN ('承認', '却下', '取消', '新規申請', '返却期限')",
            name="ck_notification_type",
        ),
        Index("idx_notification_recipient_user_id", "recipient_user_id"),
        Index("idx_notification_loan_request_id", "loan_request_id"),
        Index("idx_notification_read_flag", "read_flag"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient_user_id: Mapped[int] = mapped_column(
        ForeignKey("USER.id", name="fk_notification_recipient_user_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    notification_type: Mapped[str] = mapped_column(String, nullable=False)
    loan_request_id: Mapped[int] = mapped_column(
        ForeignKey(
            "LOAN_REQUEST.id", name="fk_notification_loan_request_id", onupdate="CASCADE", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    read_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
