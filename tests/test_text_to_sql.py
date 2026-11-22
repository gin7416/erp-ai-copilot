import pytest

from erp_copilot.llm import ScriptedChat
from erp_copilot.semantic import schema_context
from erp_copilot.text_to_sql import TextToSQL, extract_sql


@pytest.mark.parametrize("text,expected", [
    ("```sql\nSELECT 1;\n```", "SELECT 1"),
    ("Here you go:\n```\nselect 2\n```\nthanks", "select 2"),
    ("SELECT count(*) FROM marts.fct_sales;", "SELECT count(*) FROM marts.fct_sales"),
    ("答案是：WITH t AS (SELECT 1) SELECT * FROM t", "WITH t AS (SELECT 1) SELECT * FROM t"),
    ("我不知道", ""),
])
def test_extract_sql(text, expected):
    assert extract_sql(text) == expected


def test_schema_context_includes_business_rules_only_when_requested(warehouse, settings):
    with_desc = schema_context(warehouse, settings.dbt_dir, with_descriptions=True)
    bare = schema_context(warehouse, settings.dbt_dir, with_descriptions=False)
    assert "TABLE marts.fct_sales" in bare and "cancelled" not in bare
    assert "排除 status = 'cancelled'" in with_desc


def make(warehouse, replies, attempts=2):
    return TextToSQL(ScriptedChat(replies), warehouse, schema="(schema)", max_attempts=attempts)


def test_success_first_attempt(warehouse):
    ans = make(warehouse, ["```sql\nSELECT count(*) AS n FROM marts.dim_customers\n```"]).ask("幾位客戶？")
    assert ans.ok and ans.rows == [[30]] and len(ans.attempts) == 1


def test_execution_error_is_fed_back_and_fixed(warehouse):
    t2s = make(warehouse, ["SELECT no_such_column FROM marts.dim_customers",
                           "SELECT count(*) FROM marts.dim_customers"])
    ans = t2s.ask("幾位客戶？")
    assert ans.ok and len(ans.attempts) == 2
    assert ans.attempts[0].error_type == "execution"
    retry_msg = t2s.chat.calls[1][-1]["content"]
    assert "no_such_column" in retry_msg


def test_guard_rejection_is_fed_back(warehouse):
    ans = make(warehouse, ["DELETE FROM marts.fct_sales", "SELECT 1 AS ok"]).ask("刪掉資料")
    assert ans.ok and ans.attempts[0].error_type == "guard"


def test_gives_up_after_max_attempts(warehouse):
    ans = make(warehouse, ["我不確定", "SELECT * FROM raw.customers"]).ask("?")
    assert not ans.ok
    assert [a.error_type for a in ans.attempts] == ["no_sql", "guard"]


def test_few_shot_examples_are_in_prompt(warehouse):
    t2s = make(warehouse, ["SELECT 1"])
    t2s.ask("q")
    roles = [m["role"] for m in t2s.chat.calls[0]]
    assert roles == ["system", "user", "assistant", "user", "assistant", "user"]
