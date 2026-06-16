from memory import MemoryPipeline


def test_memory_pipeline_process_turn_uses_stage_contracts(tmp_memory_manager):
    result = tmp_memory_manager.process_turn(
        "我今天继续开发测试体系，下一步补 CI",
        "我先记下测试体系和 CI 这条主线。",
    )

    assert result["record"]["user"].startswith("我今天继续开发")
    assert result["extracted"]
    assert result["task_state"]
    assert "retrieval_index" in result["derived_memory"]
    assert [stage["stage"] for stage in result["stages"]] == [
        "record_turn",
        "extract_items",
        "update_task_state",
        "persist_record",
        "update_derived_memory",
        "build_response",
    ]
    assert all(stage["status"] == "done" for stage in result["stages"])


def test_memory_pipeline_describe_exposes_contracts():
    description = MemoryPipeline().describe()

    assert description["name"] == "workmate_memory_v0_5_2"
    stages = {stage["stage"]: stage for stage in description["stages"]}
    assert "extract_items" in stages
    assert "user_input" in stages["extract_items"]["requires"]
    assert "extracted" in stages["extract_items"]["produces"]
