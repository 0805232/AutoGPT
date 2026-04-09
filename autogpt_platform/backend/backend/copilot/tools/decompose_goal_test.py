"""Unit tests for DecomposeGoalTool."""

import pytest

from ._test_data import make_session
from .decompose_goal import DEFAULT_ACTION, MAX_STEPS, DecomposeGoalTool
from .models import ErrorResponse, TaskDecompositionResponse

_USER_ID = "test-user-decompose-goal"

_VALID_STEPS = [
    {"description": "Add input block", "action": "add_input"},
    {
        "description": "Add AI summarizer block",
        "action": "add_block",
        "block_name": "AI Text Generator",
    },
    {"description": "Connect blocks together", "action": "connect_blocks"},
]


@pytest.fixture()
def tool() -> DecomposeGoalTool:
    return DecomposeGoalTool()


@pytest.fixture()
def session():
    return make_session(_USER_ID)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path(tool: DecomposeGoalTool, session):
    result = await tool._execute(
        user_id=_USER_ID,
        session=session,
        goal="Build a news summarizer agent",
        steps=_VALID_STEPS,
    )

    assert isinstance(result, TaskDecompositionResponse)
    assert result.goal == "Build a news summarizer agent"
    assert len(result.steps) == 3
    assert result.step_count == 3
    assert result.requires_approval is True
    assert result.steps[0].step_id == "step_1"
    assert result.steps[0].description == "Add input block"
    assert result.steps[1].block_name == "AI Text Generator"


@pytest.mark.asyncio
async def test_step_count_matches_steps(tool: DecomposeGoalTool, session):
    """TaskDecompositionResponse.step_count must always equal len(steps)."""
    result = await tool._execute(
        user_id=_USER_ID,
        session=session,
        goal="Simple agent",
        steps=[{"description": "Only step", "action": "add_block"}],
    )
    assert isinstance(result, TaskDecompositionResponse)
    assert result.step_count == len(result.steps)


@pytest.mark.asyncio
async def test_requires_approval_always_true(tool: DecomposeGoalTool, session):
    """requires_approval must always be True regardless of kwargs."""
    result = await tool._execute(
        user_id=_USER_ID,
        session=session,
        goal="Build agent",
        steps=_VALID_STEPS,
        require_approval=False,  # should be ignored
    )
    assert isinstance(result, TaskDecompositionResponse)
    assert result.requires_approval is True


@pytest.mark.asyncio
async def test_invalid_action_defaults_to_add_block(tool: DecomposeGoalTool, session):
    """Unknown action values are coerced to DEFAULT_ACTION."""
    result = await tool._execute(
        user_id=_USER_ID,
        session=session,
        goal="Build agent",
        steps=[{"description": "Do something weird", "action": "fly_to_moon"}],
    )
    assert isinstance(result, TaskDecompositionResponse)
    assert result.steps[0].action == DEFAULT_ACTION


@pytest.mark.asyncio
async def test_block_name_optional(tool: DecomposeGoalTool, session):
    """Steps without block_name should succeed with block_name=None."""
    result = await tool._execute(
        user_id=_USER_ID,
        session=session,
        goal="Agent with no block name",
        steps=[{"description": "Configure the agent", "action": "configure"}],
    )
    assert isinstance(result, TaskDecompositionResponse)
    assert result.steps[0].block_name is None


# ---------------------------------------------------------------------------
# Validation — missing inputs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_goal_returns_error(tool: DecomposeGoalTool, session):
    result = await tool._execute(
        user_id=_USER_ID,
        session=session,
        goal=None,
        steps=_VALID_STEPS,
    )
    assert isinstance(result, ErrorResponse)
    assert result.error == "missing_goal"


@pytest.mark.asyncio
async def test_empty_goal_returns_error(tool: DecomposeGoalTool, session):
    result = await tool._execute(
        user_id=_USER_ID,
        session=session,
        goal="",
        steps=_VALID_STEPS,
    )
    assert isinstance(result, ErrorResponse)
    assert result.error == "missing_goal"


@pytest.mark.asyncio
async def test_missing_steps_returns_error(tool: DecomposeGoalTool, session):
    result = await tool._execute(
        user_id=_USER_ID,
        session=session,
        goal="Build agent",
        steps=None,
    )
    assert isinstance(result, ErrorResponse)
    assert result.error == "missing_steps"


@pytest.mark.asyncio
async def test_empty_steps_returns_error(tool: DecomposeGoalTool, session):
    result = await tool._execute(
        user_id=_USER_ID,
        session=session,
        goal="Build agent",
        steps=[],
    )
    assert isinstance(result, ErrorResponse)
    assert result.error == "missing_steps"


@pytest.mark.asyncio
async def test_too_many_steps_returns_error(tool: DecomposeGoalTool, session):
    many_steps = [
        {"description": f"Step {i}", "action": "add_block"}
        for i in range(MAX_STEPS + 1)
    ]
    result = await tool._execute(
        user_id=_USER_ID,
        session=session,
        goal="Over-engineered agent",
        steps=many_steps,
    )
    assert isinstance(result, ErrorResponse)
    assert result.error == "too_many_steps"


@pytest.mark.asyncio
async def test_exactly_max_steps_succeeds(tool: DecomposeGoalTool, session):
    """Exactly MAX_STEPS steps should succeed."""
    max_steps = [
        {"description": f"Step {i}", "action": "add_block"} for i in range(MAX_STEPS)
    ]
    result = await tool._execute(
        user_id=_USER_ID,
        session=session,
        goal="Complex agent",
        steps=max_steps,
    )
    assert isinstance(result, TaskDecompositionResponse)
    assert len(result.steps) == MAX_STEPS


# ---------------------------------------------------------------------------
# Validation — malformed step items
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_dict_step_returns_error(tool: DecomposeGoalTool, session):
    """A step that is not a dict should return an error."""
    result = await tool._execute(
        user_id=_USER_ID,
        session=session,
        goal="Build agent",
        steps=["not a dict"],  # type: ignore[list-item]
    )
    assert isinstance(result, ErrorResponse)
    assert result.error == "invalid_step"


@pytest.mark.asyncio
async def test_step_with_empty_description_returns_error(
    tool: DecomposeGoalTool, session
):
    result = await tool._execute(
        user_id=_USER_ID,
        session=session,
        goal="Build agent",
        steps=[{"description": "", "action": "add_block"}],
    )
    assert isinstance(result, ErrorResponse)
    assert result.error == "empty_description"


@pytest.mark.asyncio
async def test_step_with_missing_description_returns_error(
    tool: DecomposeGoalTool, session
):
    result = await tool._execute(
        user_id=_USER_ID,
        session=session,
        goal="Build agent",
        steps=[{"action": "add_block"}],
    )
    assert isinstance(result, ErrorResponse)
    assert result.error == "empty_description"


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_step_ids_are_sequential(tool: DecomposeGoalTool, session):
    result = await tool._execute(
        user_id=_USER_ID,
        session=session,
        goal="Build agent",
        steps=_VALID_STEPS,
    )
    assert isinstance(result, TaskDecompositionResponse)
    for i, step in enumerate(result.steps):
        assert step.step_id == f"step_{i + 1}"
