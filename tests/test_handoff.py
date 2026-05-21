from orchestrator.handoff import build_handoff_context, handoff_path, parse_issue_dependencies


def test_parse_issue_dependencies_from_metadata_block():
    deps = parse_issue_dependencies(
        """
        Implement the next step.

        ## Agent Metadata

        Depends-On: #2, #5
        Context-From: #7
        """
    )

    assert deps.depends_on == (2, 5)
    assert deps.context_from == (7,)


def test_parse_issue_dependencies_dedupes_refs():
    deps = parse_issue_dependencies("Depends-On: #2, #2\nContext-From: #2, #3")

    assert deps.depends_on == (2,)
    assert deps.context_from == (2, 3)


def test_handoff_path():
    assert handoff_path(12) == ".agent/handoffs/issue-12.md"


def test_build_handoff_context_orders_by_issue():
    context = build_handoff_context({5: "five", 2: "two"})

    assert context.index("issue #2") < context.index("issue #5")
