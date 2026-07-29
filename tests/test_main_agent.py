"""CLI entrypoint tests for main_agent.py.

main_agent.py's only logic lives inside its `if __name__ == "__main__":`
guard, so importing the module (as every other test file in this suite
does implicitly) executes nothing. These tests drive that guarded block
directly via runpy, with build_agent() and input() mocked — no real LLM
call, no real terminal needed. Excluded from the coverage gate (see
pyproject.toml) since it's an interactive entrypoint, not library code;
these tests exist as a regression safety net, not a coverage target.
"""

import runpy
from unittest.mock import MagicMock

import agent as agent_module
from conftest import make_ai_message

MAIN_AGENT_PATH = "main_agent.py"


def _run_main(monkeypatch, inputs, agent_invoke_results):
    fake_agent = MagicMock()
    fake_agent.invoke.side_effect = agent_invoke_results
    monkeypatch.setattr(agent_module, "build_agent", MagicMock(return_value=fake_agent))
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=inputs))

    runpy.run_path(MAIN_AGENT_PATH, run_name="__main__")

    return fake_agent


def test_normal_turn_prints_ai_reply_and_exits(monkeypatch, capsys):
    _run_main(
        monkeypatch,
        inputs=["What can you help me with?", "exit"],
        agent_invoke_results=[{"messages": [make_ai_message("Here is my answer.")]}],
    )

    out = capsys.readouterr().out
    assert "AI: Here is my answer." in out
    assert "Goodbye!" in out


def test_blank_input_is_skipped_without_calling_the_agent(monkeypatch, capsys):
    fake_agent = _run_main(
        monkeypatch,
        inputs=["", "exit"],
        agent_invoke_results=[],
    )

    fake_agent.invoke.assert_not_called()


def test_quit_is_accepted_as_an_alias_for_exit(monkeypatch, capsys):
    _run_main(monkeypatch, inputs=["quit"], agent_invoke_results=[])

    assert "Goodbye!" in capsys.readouterr().out


def test_agent_exception_is_caught_and_loop_continues(monkeypatch, capsys):
    fake_agent = MagicMock()
    fake_agent.invoke.side_effect = [RuntimeError("boom"), {"messages": [make_ai_message("recovered")]}]
    monkeypatch.setattr(agent_module, "build_agent", MagicMock(return_value=fake_agent))
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=["first", "second", "exit"]))

    runpy.run_path(MAIN_AGENT_PATH, run_name="__main__")

    out = capsys.readouterr().out
    assert "❌ Error: boom" in out
    assert "AI: recovered" in out
    assert "Goodbye!" in out


def test_keyboard_interrupt_exits_gracefully(monkeypatch, capsys):
    monkeypatch.setattr(agent_module, "build_agent", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=KeyboardInterrupt()))

    runpy.run_path(MAIN_AGENT_PATH, run_name="__main__")

    assert "Goodbye!" in capsys.readouterr().out


def test_chat_history_accumulates_across_turns(monkeypatch, capsys):
    # invoke() is called with a reference to the same mutable chat_history
    # list every turn, so a plain call_args_list inspection after the loop
    # ends would only ever see its *final* state. Capture a copy at call time
    # instead, via a side_effect callable, to see what each turn actually sent.
    captured_histories = []

    def fake_invoke(payload):
        captured_histories.append([dict(m) for m in payload["messages"]])
        reply = f"reply {len(captured_histories)}"
        return {"messages": [make_ai_message(reply)]}

    fake_agent = MagicMock()
    fake_agent.invoke.side_effect = fake_invoke
    monkeypatch.setattr(agent_module, "build_agent", MagicMock(return_value=fake_agent))
    monkeypatch.setattr(
        "builtins.input", MagicMock(side_effect=["first message", "second message", "exit"])
    )

    runpy.run_path(MAIN_AGENT_PATH, run_name="__main__")

    assert [m["content"] for m in captured_histories[0]] == ["first message"]
    assert [m["content"] for m in captured_histories[1]] == [
        "first message",
        "reply 1",
        "second message",
    ]
