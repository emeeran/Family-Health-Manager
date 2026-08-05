"""Unit tests for the EncryptedText SQLAlchemy TypeDecorator.

Verifies the encrypt-on-write / decrypt-on-read contract, the legacy-plaintext
passthrough (critical for the migration cutover), and None/empty handling.
"""

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select
from sqlalchemy.orm import Session

from app.db_types import EncryptedText


def _table_with(metadata: MetaData) -> Table:
    return Table(
        "enc_test",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("secret", EncryptedText),
    )


def test_round_trip_encrypts_on_write_decrypts_on_read():
    engine = create_engine("sqlite://")
    md = MetaData()
    tbl = _table_with(md)
    md.create_all(engine)
    with Session(engine) as s:
        s.execute(tbl.insert(), {"id": 1, "secret": "diagnosis: hypertension"})
        s.commit()
        # ORM/plain select yields plaintext (process_result_value decrypts).
        val = s.scalar(select(tbl.c.secret).where(tbl.c.id == 1))
        assert val == "diagnosis: hypertension"


def test_on_disk_value_is_ciphertext_not_plaintext():
    """The raw stored column must not contain the plaintext."""
    engine = create_engine("sqlite://")
    md = MetaData()
    tbl = _table_with(md)
    md.create_all(engine)
    plaintext = "secret PHI value"
    with Session(engine) as s:
        s.execute(tbl.insert(), {"id": 1, "secret": plaintext})
        s.commit()
        # Read the column via a core connection WITHOUT the TypeDecorator, so we
        # see the raw stored bytes (cast to a plain Text column).
        raw_tbl = Table("enc_test", MetaData(), Column("secret", String), autoload_with=engine)
        raw = s.scalar(select(raw_tbl.c.secret).where(raw_tbl.c.id == 1))
    assert raw != plaintext
    assert plaintext not in raw  # ciphertext doesn't contain the plaintext substring


def test_legacy_plaintext_reads_through_unchanged():
    """A pre-migration plaintext value must read as plaintext (passthrough)."""
    engine = create_engine("sqlite://")
    md = MetaData()
    tbl = _table_with(md)
    md.create_all(engine)
    plaintext = "legacy-plaintext-row"
    with Session(engine) as s:
        # Insert via a reflected plain-Text view (bypasses process_bind_param) so
        # the stored value is raw plaintext, simulating a pre-migration row.
        raw_tbl = Table("enc_test", MetaData(), autoload_with=engine)
        s.execute(raw_tbl.insert(), {"id": 1, "secret": plaintext})
        s.commit()
        val = s.scalar(select(tbl.c.secret).where(tbl.c.id == 1))
    assert val == plaintext


def test_none_and_empty_pass_through():
    engine = create_engine("sqlite://")
    md = MetaData()
    tbl = _table_with(md)
    md.create_all(engine)
    with Session(engine) as s:
        s.execute(tbl.insert(), [{"id": 1, "secret": None}, {"id": 2, "secret": ""}])
        s.commit()
        assert s.scalar(select(tbl.c.secret).where(tbl.c.id == 1)) is None
        assert s.scalar(select(tbl.c.secret).where(tbl.c.id == 2)) == ""


def test_cache_ok_is_set():
    assert EncryptedText.cache_ok is True
