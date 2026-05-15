from orchestrator.webhook import extract_issue_job, newly_added_agent_label


def issue_payload(previous_labels, current_labels):
    return {
        "object_kind": "issue",
        "project": {
            "id": 123,
            "path_with_namespace": "group/project",
            "git_http_url": "http://gitlab.example/group/project.git",
            "default_branch": "main",
        },
        "object_attributes": {
            "iid": 23,
            "project_id": 123,
            "title": "Add validation",
            "description": "Implement validation",
        },
        "changes": {
            "labels": {
                "previous": [{"title": label} for label in previous_labels],
                "current": [{"title": label} for label in current_labels],
            }
        },
    }


def test_new_opencode_label_triggers():
    payload = issue_payload([], ["agent:opencode"])
    assert newly_added_agent_label(payload, "agent:opencode") == ("agent:opencode", "opencode")


def test_new_codex_label_triggers():
    payload = issue_payload([], ["agent:codex"])
    assert newly_added_agent_label(payload, "agent:opencode") == ("agent:codex", "codex")


def test_new_gemini_label_triggers():
    payload = issue_payload([], ["agent:gemini"])
    assert newly_added_agent_label(payload, "agent:opencode") == ("agent:gemini", "gemini-cli")


def test_existing_label_does_not_retrigger():
    payload = issue_payload(["agent:opencode"], ["agent:opencode", "bug"])
    assert newly_added_agent_label(payload, "agent:opencode") is None


def test_unrelated_label_does_not_trigger():
    payload = issue_payload([], ["bug"])
    assert newly_added_agent_label(payload, "agent:opencode") is None


def test_issue_creation_with_agent_label_triggers_without_changes_block():
    payload = issue_payload([], ["agent:opencode"])
    payload.pop("changes")
    payload["object_attributes"]["labels"] = [{"title": "agent:opencode"}]
    assert newly_added_agent_label(payload, "agent:opencode") == ("agent:opencode", "opencode")


def test_extract_issue_job():
    payload = issue_payload([], ["agent:opencode"])
    data = extract_issue_job(payload, "agent:opencode", "opencode")
    assert data["project_id"] == 123
    assert data["issue_iid"] == 23
    assert data["repo_http_url"] == "http://gitlab.example/group/project.git"
