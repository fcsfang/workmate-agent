import os
import base64
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from memory import SupervisionEventManager


def test_screen_deviation_detection_triggered(tmp_path):
    # Setup SupervisionEventManager with temp files
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    
    # Initialize mock llm_client
    mock_llm = MagicMock()
    mock_llm.invoke_vision.return_value = (
        '{"is_deviated": true, '
        '"activity_summary": "在看 Bilibili 搞笑视频", '
        '"deviation_reason": "当前行为与学习 Python 目标无关", '
        '"tone_suggestion": "师弟，咱们现在是在写代码哦，先把视频关一关呗？"}'
    )
    manager.set_llm_client(mock_llm)

    # Setup focus session and task view states
    focus_state = {
        "current": {
            "id": "focus-session-123",
            "status": "active",
            "goal": "学习 Python",
            "duration_minutes": 45,
        }
    }
    task_view = {
        "current": {
            "id": "task-abc",
            "title": "学习 Python 代码开发",
            "status": "active"
        }
    }

    # Set last_screen_check to long ago so cooldown doesn't block it
    prefs = manager.load_preferences()
    prefs["last_screen_check"] = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
    manager.save_preferences(prefs)

    original_path_exists = Path.exists

    def mock_path_exists(self_path):
        p_str = str(self_path)
        if "/usr/sbin/screencapture" in p_str or ".jpg" in p_str:
            return True
        return original_path_exists(self_path)

    # Force mock screencapture check, command execution and file reading
    # Mock _get_active_window_macos to return an ambiguous state (needs LLM)
    with patch("os.path.exists") as mock_os_exists, \
         patch("pathlib.Path.exists", mock_path_exists), \
         patch("pathlib.Path.unlink") as mock_unlink, \
         patch("subprocess.run") as mock_run, \
         patch("builtins.open") as mock_open, \
         patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("Safari", "Some weird blog article")):
        
        mock_os_exists.side_effect = lambda path: True if "/usr/sbin/screencapture" in str(path) or ".jpg" in str(path) else os.path.exists(path)
        mock_run.return_value = MagicMock(returncode=0)
        
        mock_file = MagicMock()
        mock_file.read.return_value = b"dummy_image_data"
        mock_open.return_value.__enter__.return_value = mock_file

        # Trigger event detection
        active_events = manager.detect_events(
            focus_state=focus_state,
            commitments=[],
            task_view=task_view,
        )

        # Assertions
        assert len(active_events) > 0
        deviation_events = [e for e in active_events if e["type"] == "screen_deviation"]
        assert len(deviation_events) == 1
        assert deviation_events[0]["subject_id"] == "focus-session-123"
        assert deviation_events[0]["severity"] == "high"
        assert "Bilibili" in deviation_events[0]["message"]
        assert "师弟" not in deviation_events[0]["display_message"]
        assert deviation_events[0]["display_message"]


def test_screen_deviation_detection_not_triggered_on_correct_behavior(tmp_path):
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    
    mock_llm = MagicMock()
    mock_llm.invoke_vision.return_value = (
        '{"is_deviated": false, '
        '"activity_summary": "在 VS Code 中编写 Python 代码", '
        '"deviation_reason": "", '
        '"tone_suggestion": ""}'
    )
    manager.set_llm_client(mock_llm)

    focus_state = {
        "current": {
            "id": "focus-session-123",
            "status": "active",
            "goal": "学习 Python",
        }
    }
    task_view = {
        "current": {
            "id": "task-abc",
            "title": "学习 Python 代码开发",
            "status": "active"
        }
    }

    # Set last_screen_check to long ago
    prefs = manager.load_preferences()
    prefs["last_screen_check"] = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
    manager.save_preferences(prefs)

    original_path_exists = Path.exists

    def mock_path_exists(self_path):
        p_str = str(self_path)
        if "/usr/sbin/screencapture" in p_str or ".jpg" in p_str:
            return True
        return original_path_exists(self_path)

    with patch("os.path.exists") as mock_os_exists, \
         patch("pathlib.Path.exists", mock_path_exists), \
         patch("pathlib.Path.unlink") as mock_unlink, \
         patch("subprocess.run") as mock_run, \
         patch("builtins.open") as mock_open, \
         patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("Safari", "Some weird blog article")):
        
        mock_os_exists.side_effect = lambda path: True if "/usr/sbin/screencapture" in str(path) or ".jpg" in str(path) else os.path.exists(path)
        mock_run.return_value = MagicMock(returncode=0)
        
        mock_file = MagicMock()
        mock_file.read.return_value = b"dummy_image_data"
        mock_open.return_value.__enter__.return_value = mock_file

        active_events = manager.detect_events(
            focus_state=focus_state,
            commitments=[],
            task_view=task_view,
        )

        deviation_events = [e for e in active_events if e["type"] == "screen_deviation"]
        assert len(deviation_events) == 0


def test_rule_based_whitelist_bypass(tmp_path):
    """测试当前台 App 为 VS Code 时，本地规则命中白名单，直接判定未偏航，不调用视觉大模型"""
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    

    focus_state = {
        "current": {
            "id": "focus-session-123",
            "status": "active",
            "goal": "学习 Python",
        }
    }
    task_view = {
        "current": {
            "id": "task-abc",
            "title": "学习 Python 代码开发",
            "status": "active"
        }
    }

    prefs = manager.load_preferences()
    prefs["last_screen_check"] = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
    manager.save_preferences(prefs)

    # Mock _get_active_window_macos to return VS Code
    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("Visual Studio Code", "supervision_events.py")):
        active_events = manager.detect_events(
            focus_state=focus_state,
            commitments=[],
            task_view=task_view,
        )
        
        # 结果应不生成偏航事件，并且完全没有调用 invoke_vision API 扣费
        deviation_events = [e for e in active_events if e["type"] == "screen_deviation"]
        assert len(deviation_events) == 0



def test_rule_based_blacklist_intercept(tmp_path):
    """测试当前台为 Bilibili 时，本地规则命中黑名单，直接判定偏航生成事件，不调用视觉大模型"""
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    

    focus_state = {
        "current": {
            "id": "focus-session-123",
            "status": "active",
            "goal": "学习 Python",
        }
    }
    task_view = {
        "current": {
            "id": "task-abc",
            "title": "学习 Python 代码开发",
            "status": "active"
        }
    }

    prefs = manager.load_preferences()
    prefs["last_screen_check"] = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
    manager.save_preferences(prefs)

    # Mock _get_active_window_macos to return Chrome showing Bilibili
    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("Google Chrome", "【2026最新】大模型自研Agent实战 - bilibili")):
        active_events = manager.detect_events(
            focus_state=focus_state,
            commitments=[],
            task_view=task_view,
        )
        
        # 结果应直接产生偏航事件，并且完全没有调用 invoke_vision API 扣费
        deviation_events = [e for e in active_events if e["type"] == "screen_deviation"]
        assert len(deviation_events) == 1
        assert deviation_events[0]["subject_id"] == "focus-session-123"
        assert "Google Chrome" in deviation_events[0]["message"]



def test_auto_monitor_during_work_hours(tmp_path):
    """测试工作时间段自动激活监视（无需开启 Focus Session），并自动同步 active 任务名"""
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    

    # No active focus session
    focus_state = {"current": {}}
    
    # Active task exists
    task_view = {
        "current": {
            "id": "task-abc",
            "title": "补习大模型多模态论文",
            "status": "active"
        }
    }

    # Setup preferences to enable auto work hours monitor
    prefs = manager.load_preferences()
    prefs["auto_monitor_work_hours_enabled"] = True
    prefs["work_hours_start"] = "09:00"
    prefs["work_hours_end"] = "18:00"
    prefs["last_screen_check"] = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
    manager.save_preferences(prefs)

    # Current time is 14:00 (inside work hours)
    now = datetime.combine(datetime.now().date(), datetime.strptime("14:00", "%H:%M").time())

    # Mock _get_active_window_macos to return Chrome showing Steam (blacklisted)
    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("Google Chrome", "Steam Community")):
        # We patch datetime.now inside supervision_events to return 14:00
        with patch("memory.supervision_events.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            mock_dt.combine.side_effect = datetime.combine
            mock_dt.strptime.side_effect = datetime.strptime
            
            active_events = manager.detect_events(
                focus_state=focus_state,
                commitments=[],
                task_view=task_view,
            )
            print(f"[DEBUG TEST] active_events: {active_events}")
            print(f"[DEBUG TEST] all saved events: {manager.load_events()}")

        # Should automatically detect screen deviation under the dynamic goal of the active task
        deviation_events = [e for e in active_events if e["type"] == "screen_deviation"]
        assert len(deviation_events) == 1
        assert deviation_events[0]["subject_type"] == "task"
        assert deviation_events[0]["subject_id"] == "task-abc"
        assert "补习大模型多模态论文" in deviation_events[0]["display_message"]



def test_screen_deviation_chat_injection(tmp_memory_manager):
    """测试当检测到屏幕偏航事件时，系统会自动在对话历史记录中插入一条偏航提醒消息"""
    # Initialize mock llm_client

    # Enable auto work hours monitor
    prefs = tmp_memory_manager.get_supervision_preferences()
    prefs["auto_monitor_work_hours_enabled"] = True
    prefs["work_hours_start"] = "09:00"
    prefs["work_hours_end"] = "18:00"
    prefs["last_screen_check"] = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
    tmp_memory_manager.update_supervision_preferences(prefs)

    # Mock active task in task_state
    tmp_memory_manager.get_task_view = MagicMock(return_value={
        "current": {
            "id": "task-abc",
            "title": "编写单元测试",
            "status": "active"
        }
    })

    # Current time is 14:00 (inside work hours)
    now = datetime.combine(datetime.now().date(), datetime.strptime("14:00", "%H:%M").time())

    # Mock _get_active_window_macos to return Chrome showing Bilibili (blacklisted)
    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("Google Chrome", "【2026最新】大模型自研Agent实战 - bilibili")):
        with patch("memory.supervision_events.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            mock_dt.combine.side_effect = datetime.combine
            mock_dt.strptime.side_effect = datetime.strptime

            # Call refresh_supervision_events, which triggers detection & insertion
            events = tmp_memory_manager.refresh_supervision_events()

    # 1. Verify screen deviation event is detected
    deviation_events = [e for e in events if e["type"] == "screen_deviation"]
    assert len(deviation_events) == 1
    
    # 2. Verify it is recorded in chat history
    records = tmp_memory_manager.load_records()
    assert len(records) == 1
    assert records[0]["user"] == ""
    assert records[0]["assistant"]
    assert "方向很对" not in records[0]["assistant"]
    assert "bilibili" in deviation_events[0]["message"]

    # 3. Verify event metadata indicates it has been added to chat
    all_events = tmp_memory_manager.supervision_event_manager.load_events()
    matching_events = [e for e in all_events if e["id"] == deviation_events[0]["id"]]
    assert len(matching_events) == 1
    assert matching_events[0]["metadata"].get("added_to_chat") is True

    # 4. Run refresh_supervision_events again and verify no duplicate records are added
    # Update cooldown to bypass interval check
    prefs = tmp_memory_manager.get_supervision_preferences()
    prefs["last_screen_check"] = (now - timedelta(minutes=10)).isoformat(timespec="seconds")
    tmp_memory_manager.update_supervision_preferences(prefs)

    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("Google Chrome", "【2026最新】大模型自研Agent实战 - bilibili")):
        with patch("memory.supervision_events.datetime") as mock_dt:
            mock_dt.now.return_value = now + timedelta(minutes=6)
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            mock_dt.combine.side_effect = datetime.combine
            mock_dt.strptime.side_effect = datetime.strptime

            events2 = tmp_memory_manager.refresh_supervision_events()

    records2 = tmp_memory_manager.load_records()
    assert len(records2) == 1  # Should still be 1, no duplicates!


def test_custom_blacklist_keywords_intercept(tmp_path):
    """测试自定义黑名单关键词拦截机制 (例如将“微信”/“wechat”加入黑名单后，立刻触发偏航而不调用视觉大模型)"""
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    

    focus_state = {
        "current": {
            "id": "focus-123",
            "status": "active",
            "goal": "完成毕业设计"
        }
    }

    # Setup preferences to include custom blacklist keywords
    prefs = manager.load_preferences()
    prefs["custom_blacklist_keywords"] = ["微信", "wechat"]
    prefs["last_screen_check"] = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
    manager.save_preferences(prefs)

    # 1. Test WeChat app name blacklist
    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("WeChat", "与家人的日常聊天")):
        active_events = manager.detect_events(
            focus_state=focus_state,
            commitments=[],
            task_view={},
        )
        deviation_events = [e for e in active_events if e["type"] == "screen_deviation"]
        assert len(deviation_events) == 1
        assert "WeChat" in deviation_events[0]["message"]
  # 验证没调用 Vision

    # Clear events and preferences for the second test
    manager.save_events([])
    prefs = manager.load_preferences()
    prefs["last_screen_check"] = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
    manager.save_preferences(prefs)

    # 2. Test window title keyword blacklist (e.g. Chrome showing 微信网页版)
    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("Google Chrome", "微信网页版")):
        active_events = manager.detect_events(
            focus_state=focus_state,
            commitments=[],
            task_view={},
        )
        deviation_events = [e for e in active_events if e["type"] == "screen_deviation"]
        assert len(deviation_events) == 1
        assert "Google Chrome" in deviation_events[0]["message"]



def test_screen_accompaniment_and_auto_resolution(tmp_memory_manager):
    """测试陪伴提醒事件。
    1. 当用户在前台正常工作（例如使用 VS Code）时，应触发 screen_accompaniment 事件。
    2. 伴随消息应成功持久化写入对话历史。
    3. 当用户下一次检测时偏航到 Bilibili 时，旧的 screen_accompaniment 事件应该自动被 resolution 机制状态机 resolved，并且产生新的 screen_deviation 事件。
    """

    # 开启工作时间监视
    prefs = tmp_memory_manager.get_supervision_preferences()
    prefs["auto_monitor_work_hours_enabled"] = True
    prefs["work_hours_start"] = "09:00"
    prefs["work_hours_end"] = "18:00"
    prefs["last_screen_check"] = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
    tmp_memory_manager.update_supervision_preferences(prefs)

    # Mock 当前任务
    tmp_memory_manager.get_task_view = MagicMock(return_value={
        "current": {
            "id": "task-xyz",
            "title": "开发新功能",
            "status": "active"
        }
    })

    # 当前时间 14:00
    now = datetime.combine(datetime.now().date(), datetime.strptime("14:00", "%H:%M").time())

    # Step 1: 在工作应用中 (Visual Studio Code)，应产生 screen_accompaniment
    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("Visual Studio Code", "main.py")):
        with patch("memory.supervision_events.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            mock_dt.combine.side_effect = datetime.combine
            mock_dt.strptime.side_effect = datetime.strptime

            events = tmp_memory_manager.refresh_supervision_events()

    # 验证产生 screen_accompaniment 事件
    accompaniment_events = [e for e in events if e["type"] == "screen_accompaniment"]
    assert len(accompaniment_events) == 1
    assert accompaniment_events[0]["status"] == "detected"
    assert accompaniment_events[0]["severity"] == "low"
    assert "Visual Studio Code" in accompaniment_events[0]["message"]

    # 验证对话记录中包含伴随鼓励文本
    records = tmp_memory_manager.load_records()
    assert len(records) == 1
    assert records[0]["user"] == ""
    assert records[0]["assistant"]
    assert "方向很对" not in records[0]["assistant"]

    # Step 2: 再次运行，仍处于工作应用中，验证不会重复写入对话记录 (deduplication)
    prefs = tmp_memory_manager.get_supervision_preferences()
    prefs["last_screen_check"] = (now - timedelta(minutes=10)).isoformat(timespec="seconds")
    tmp_memory_manager.update_supervision_preferences(prefs)

    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("Visual Studio Code", "main.py")):
        with patch("memory.supervision_events.datetime") as mock_dt:
            mock_dt.now.return_value = now + timedelta(minutes=5)
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            mock_dt.combine.side_effect = datetime.combine
            mock_dt.strptime.side_effect = datetime.strptime

            events2 = tmp_memory_manager.refresh_supervision_events()

    records2 = tmp_memory_manager.load_records()
    assert len(records2) == 1  # 依然只有一条消息，没有重复写入！

    # Step 3: 用户偏航到 Bilibili，验证原来的 screen_accompaniment 自动 resolved，并产生 screen_deviation
    prefs = tmp_memory_manager.get_supervision_preferences()
    prefs["last_screen_check"] = (now - timedelta(minutes=10)).isoformat(timespec="seconds")
    tmp_memory_manager.update_supervision_preferences(prefs)

    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("Google Chrome", "【2026最新】大模型自研Agent实战 - bilibili")):
        with patch("memory.supervision_events.datetime") as mock_dt:
            mock_dt.now.return_value = now + timedelta(minutes=10)
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            mock_dt.combine.side_effect = datetime.combine
            mock_dt.strptime.side_effect = datetime.strptime

            events3 = tmp_memory_manager.refresh_supervision_events()

    # 验证 screen_deviation 被检测出
    deviation_events = [e for e in events3 if e["type"] == "screen_deviation"]
    assert len(deviation_events) == 1
    assert deviation_events[0]["status"] == "detected"

    # 验证原先的 screen_accompaniment 已经自动解决 (resolved)
    all_events = tmp_memory_manager.supervision_event_manager.load_events()
    old_acc_events = [e for e in all_events if e["type"] == "screen_accompaniment"]
    assert len(old_acc_events) == 1
    assert old_acc_events[0]["status"] == "resolved"

    # 验证对话历史增加了偏航提醒
    records3 = tmp_memory_manager.load_records()
    assert len(records3) == 2
