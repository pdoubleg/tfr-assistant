from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


async def run_sqlite_health_checks(engine: AsyncEngine) -> dict[str, list[dict[str, object]]]:
    async with engine.connect() as connection:
        integrity_rows = (await connection.execute(text("PRAGMA integrity_check"))).mappings().all()

        foreign_key_rows = (
            (await connection.execute(text("PRAGMA foreign_key_check"))).mappings().all()
        )

    return {
        "integrity_check": [dict(row) for row in integrity_rows],
        "foreign_key_check": [dict(row) for row in foreign_key_rows],
    }


async def find_orphaned_audit_reviews(session: AsyncSession) -> list[dict[str, object]]:
    result = await session.execute(
        text(
            """
            SELECT r.id, r.batch_id
            FROM audit_reviews AS r
            LEFT JOIN audit_batches AS b
                ON r.batch_id = b.id
            WHERE r.batch_id IS NOT NULL
              AND b.id IS NULL
            """
        )
    )
    return [dict(row) for row in result.mappings().all()]


async def find_orphaned_result_versions(session: AsyncSession) -> list[dict[str, object]]:
    result = await session.execute(
        text(
            """
            SELECT v.id, v.review_id
            FROM audit_result_versions AS v
            LEFT JOIN audit_reviews AS r
                ON v.review_id = r.id
            WHERE r.id IS NULL
            """
        )
    )
    return [dict(row) for row in result.mappings().all()]


async def find_orphaned_result_items(session: AsyncSession) -> list[dict[str, object]]:
    result = await session.execute(
        text(
            """
            SELECT item.id, item.result_version_id, item.review_id
            FROM audit_result_items AS item
            LEFT JOIN audit_result_versions AS v
                ON item.result_version_id = v.id
            LEFT JOIN audit_reviews AS r
                ON item.review_id = r.id
            WHERE v.id IS NULL
               OR r.id IS NULL
            """
        )
    )
    return [dict(row) for row in result.mappings().all()]


async def find_orphaned_result_texts(session: AsyncSession) -> list[dict[str, object]]:
    result = await session.execute(
        text(
            """
            SELECT txt.id, txt.result_version_id, txt.review_id
            FROM audit_result_texts AS txt
            LEFT JOIN audit_result_versions AS v
                ON txt.result_version_id = v.id
            LEFT JOIN audit_reviews AS r
                ON txt.review_id = r.id
            WHERE v.id IS NULL
               OR r.id IS NULL
            """
        )
    )
    return [dict(row) for row in result.mappings().all()]
