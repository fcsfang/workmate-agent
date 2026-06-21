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
        '{"observation": "在看 Bilibili 搞笑视频", '
        '"goal_note": "这和学习 Python 这条线有点分开了", '
        '"message_type": "pullback", '
        '"should_message": true, '
        '"message": "我看到你现在在看 Bilibili，和学习 Python 这条线有点分开了。先回来吧。"}'
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
    prefs["last_screen_check"] = (datetime.now() - timedelta(minutes=120)).isoformat(timespec="seconds")
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
        assert deviation_events[0]["display_message"] == "我看到你现在在看 Bilibili，和学习 Python 这条线有点分开了。先回来吧。"
        assert deviation_events[0]["metadata"]["vision_direct_message"] == "我看到你现在在看 Bilibili，和学习 Python 这条线有点分开了。先回来吧。"
        assert deviation_events[0]["metadata"]["reminder_generated_by"] == "vision_direct"
        vision_prompt = mock_llm.invoke_vision.call_args.args[0]
        assert "文案不限制长度" in vision_prompt
        assert "message_type" in vision_prompt
        assert "不限制长度" in vision_prompt
        assert "confidence" not in vision_prompt
        assert "deviation_level" not in vision_prompt
        assert "tone_suggestion" not in vision_prompt
        # Check that json_mode=True was supplied
        assert mock_llm.invoke_vision.call_args.kwargs.get("json_mode") is True
        mock_llm.invoke_raw.assert_not_called()


def test_screen_deviation_detection_not_triggered_on_correct_behavior(tmp_path):
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    
    mock_llm = MagicMock()
    mock_llm.invoke_vision.return_value = (
        '{"observation": "在 VS Code 中编写 Python 代码", '
        '"goal_note": "这和学习 Python 代码开发直接相关", '
        '"message_type": "silent", '
        '"should_message": false, '
        '"message": ""}'
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
    prefs["last_screen_check"] = (datetime.now() - timedelta(minutes=120)).isoformat(timespec="seconds")
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


def test_manual_screen_check_always_returns_visible_companion_message(tmp_path):
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    mock_llm = MagicMock()
    mock_llm.invoke_vision.return_value = (
        '{"observation": "正在阅读《深度工作》", '
        '"goal_note": "与读书分享主线一致", '
        '"message_type": "silent", '
        '"should_message": false, '
        '"message": ""}'
    )
    manager.set_llm_client(mock_llm)

    original_path_exists = Path.exists

    def mock_path_exists(self_path):
        path_text = str(self_path)
        if "/usr/sbin/screencapture" in path_text or ".jpg" in path_text:
            return True
        return original_path_exists(self_path)

    with patch("os.path.exists", return_value=True), \
         patch("pathlib.Path.exists", mock_path_exists), \
         patch("pathlib.Path.unlink"), \
         patch("subprocess.run", return_value=MagicMock(returncode=0)), \
         patch("builtins.open") as mock_open, \
         patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("WeRead", "微信读书")):
        mock_file = MagicMock()
        mock_file.read.return_value = b"dummy_image_data"
        mock_open.return_value.__enter__.return_value = mock_file

        active_events = manager.detect_events(
            focus_state={},
            commitments=[],
            task_view={
                "current": {
                    "id": "task-reading",
                    "title": "准备《深度工作》读书分享",
                    "status": "active",
                }
            },
            force_screen=True,
        )

    accompaniment = [event for event in active_events if event["type"] == "screen_accompaniment"]
    assert len(accompaniment) == 1
    assert accompaniment[0]["display_message"] == "正在阅读《深度工作》"
    assert accompaniment[0]["metadata"]["message_type"] == "companion"
    assert accompaniment[0]["metadata"]["should_message"] is True
    assert accompaniment[0]["metadata"]["triggered_by"] == "manual_screen_check"
    vision_prompt = mock_llm.invoke_vision.call_args.args[0]
    assert "用户刚刚主动点击了‘观察屏幕’" in vision_prompt
    assert "不要选择 silent" in vision_prompt


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
    prefs["last_screen_check"] = (datetime.now() - timedelta(minutes=120)).isoformat(timespec="seconds")
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
    prefs["last_screen_check"] = (datetime.now() - timedelta(minutes=120)).isoformat(timespec="seconds")
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

    # Current time is 14:00 (inside work hours)
    now = datetime.combine(datetime.now().date(), datetime.strptime("14:00", "%H:%M").time())

    # Setup preferences to enable auto work hours monitor
    prefs = manager.load_preferences()
    prefs["auto_monitor_work_hours_enabled"] = True
    prefs["work_hours_start"] = "09:00"
    prefs["work_hours_end"] = "18:00"
    prefs["last_screen_check"] = (now - timedelta(minutes=10)).isoformat(timespec="seconds")
    manager.save_preferences(prefs)

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



def test_screen_deviation_transient_chat_injection(tmp_memory_manager):
    """屏幕偏航提醒只进入临时监督消息，不写入长期对话记忆。"""
    # Initialize mock llm_client

    # Current time is 14:00 (inside work hours)
    now = datetime.combine(datetime.now().date(), datetime.strptime("14:00", "%H:%M").time())

    # Enable auto work hours monitor
    prefs = tmp_memory_manager.get_supervision_preferences()
    prefs["auto_monitor_work_hours_enabled"] = True
    prefs["work_hours_start"] = "09:00"
    prefs["work_hours_end"] = "18:00"
    prefs["last_screen_check"] = (now - timedelta(minutes=10)).isoformat(timespec="seconds")
    tmp_memory_manager.update_supervision_preferences(prefs)

    # Mock active task in task_state
    tmp_memory_manager.get_task_view = MagicMock(return_value={
        "current": {
            "id": "task-abc",
            "title": "编写单元测试",
            "status": "active"
        }
    })

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
    
    # 2. Verify it is visible as transient supervision message, not long-term record
    records = tmp_memory_manager.load_records()
    assert records == []
    supervision_messages = tmp_memory_manager.load_supervision_messages()
    assert len(supervision_messages) == 1
    assert supervision_messages[0]["user"] == ""
    assert supervision_messages[0]["assistant"]
    assert supervision_messages[0]["is_supervision"] is True
    assert supervision_messages[0]["transient"] is True
    assert "方向很对" not in supervision_messages[0]["assistant"]
    recent = tmp_memory_manager.recent_records_with_transient_supervision()
    assert len(recent) == 1
    assert recent[0]["transient"] is True
    assert "bilibili" in deviation_events[0]["message"]

    # 3. Verify event metadata indicates it has been added to chat
    all_events = tmp_memory_manager.supervision_event_manager.load_events()
    matching_events = [e for e in all_events if e["id"] == deviation_events[0]["id"]]
    assert len(matching_events) == 1
    assert matching_events[0]["metadata"].get("added_to_transient_chat") is True

    # 4. Run refresh_supervision_events again and verify no duplicate transient messages are added
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
    assert records2 == []
    assert len(tmp_memory_manager.load_supervision_messages()) == 1


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
    prefs["last_screen_check"] = (datetime.now() - timedelta(minutes=120)).isoformat(timespec="seconds")
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

    manager.save_events([])
    prefs = manager.load_preferences()
    prefs["last_screen_check"] = (datetime.now() - timedelta(minutes=120)).isoformat(timespec="seconds")
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

    # Current time 14:00
    now = datetime.combine(datetime.now().date(), datetime.strptime("14:00", "%H:%M").time())

    # 开启工作时间监视
    prefs = tmp_memory_manager.get_supervision_preferences()
    prefs["auto_monitor_work_hours_enabled"] = True
    prefs["work_hours_start"] = "09:00"
    prefs["work_hours_end"] = "18:00"
    prefs["last_screen_check"] = (now - timedelta(minutes=120)).isoformat(timespec="seconds")
    tmp_memory_manager.update_supervision_preferences(prefs)

    # Mock 当前任务
    tmp_memory_manager.get_task_view = MagicMock(return_value={
        "current": {
            "id": "task-xyz",
            "title": "开发新功能",
            "status": "active"
        }
    })

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

    # Vision 提醒只进入短期监督消息，不污染长期对话记录。
    records = tmp_memory_manager.load_records()
    messages = tmp_memory_manager.load_supervision_messages()
    assert records == []
    assert len(messages) == 1
    assert messages[0]["assistant"]
    assert "方向很对" not in messages[0]["assistant"]

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

    messages2 = tmp_memory_manager.load_supervision_messages()
    assert len(messages2) == 1

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

    # 验证短期监督消息增加了偏航提醒，长期 records 仍为空。
    messages3 = tmp_memory_manager.load_supervision_messages()
    assert len(messages3) == 2
    assert tmp_memory_manager.load_records() == []


def test_adaptive_screen_monitor_cooldown(tmp_path):
    """测试自适应检测频率判定逻辑：
    1. 当上一次监测结果为 pullback 时，频率应自动缩减（缩短为原基础 5m 的 40% = 2m）。
    2. 当上一次监测结果为 companion 时，频率应自动舒张（延长为原基础 5m 的 1.5 倍 = 7.5m）。
    3. 当上一次监测结果超时（超过 30m）时，应该退回默认基础的 5m 判定。
    """
    manager = SupervisionEventManager(
        events_path=str(tmp_path / "events.json"),
        preferences_path=str(tmp_path / "preferences.json"),
    )
    
    # 模拟专注会话状态
    focus_state = {
        "current": {
            "id": "focus-123",
            "status": "active",
            "goal": "学习 Python",
        }
    }
    
    # 基本配置，interval = 5m
    prefs = manager.load_preferences()
    prefs["screen_monitor_enabled"] = True
    prefs["screen_monitor_interval_minutes"] = 5
    manager.save_preferences(prefs)

    # 1. 模拟上一次观察是 pullback
    base_time = datetime.now()
    manager.save_screen_observations([
        {
            "id": "obs-1",
            "observed_at": base_time.isoformat(timespec="seconds"),
            "subject_id": "focus-123",
            "message_type": "pullback",
            "should_message": True,
            "message": "偏航啦",
        }
    ])

    # 冷却时间判定：
    # 距离上次观测 2.5 分钟后触发下一次检测 (2.5m > 2.0m, 所以自适应判定不应被冷却拦截)
    now_pullback_not_blocked = base_time + timedelta(minutes=2, seconds=30)
    prefs["last_screen_check"] = base_time.isoformat(timespec="seconds")
    manager.save_preferences(prefs)

    # Mock AppleScript 命中黑名单，退回本地直接偏航，防止调用大模型
    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("Google Chrome", "Steam Community")), \
         patch("memory.supervision_events.datetime") as mock_dt:
        mock_dt.now.return_value = now_pullback_not_blocked
        mock_dt.fromisoformat.side_effect = datetime.fromisoformat
        mock_dt.combine.side_effect = datetime.combine
        mock_dt.strptime.side_effect = datetime.strptime

        active_events = manager.detect_events(
            focus_state=focus_state,
            commitments=[],
            task_view={},
        )
    # pullback 状态下缩短冷却判定（2m），所以在 2.5m 时已经能够正常触发事件，不被冷却跳过
    deviation_events = [e for e in active_events if e["type"] == "screen_deviation"]
    assert len(deviation_events) == 1

    # 2. 模拟上一次观察是 companion
    manager.save_events([])
    manager.save_screen_observations([
        {
            "id": "obs-2",
            "observed_at": base_time.isoformat(timespec="seconds"),
            "subject_id": "focus-123",
            "message_type": "companion",
            "should_message": True,
            "message": "做得很棒",
        }
    ])

    # 冷却时间判定：
    # 距离上次观测 6.0 分钟后触发下一次检测 (6.0m < 7.5m, 应该被自适应冷却拦截)
    now_companion_blocked = base_time + timedelta(minutes=6)
    prefs["last_screen_check"] = base_time.isoformat(timespec="seconds")
    manager.save_preferences(prefs)

    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("Google Chrome", "Steam Community")), \
         patch("memory.supervision_events.datetime") as mock_dt:
        mock_dt.now.return_value = now_companion_blocked
        mock_dt.fromisoformat.side_effect = datetime.fromisoformat
        mock_dt.combine.side_effect = datetime.combine
        mock_dt.strptime.side_effect = datetime.strptime

        active_events = manager.detect_events(
            focus_state=focus_state,
            commitments=[],
            task_view={},
        )
    # companion 状态下延展冷却判定（7.5m），所以在 6m 时触发检测会被冷却拦截，无法触发事件
    deviation_events = [e for e in active_events if e["type"] == "screen_deviation"]
    assert len(deviation_events) == 0

    # 3. 模拟上一次观察超时（超过 30m）
    manager.save_screen_observations([
        {
            "id": "obs-3",
            "observed_at": base_time.isoformat(timespec="seconds"),
            "subject_id": "focus-123",
            "message_type": "pullback",
            "should_message": True,
            "message": "偏航啦",
        }
    ])

    # 冷却时间判定：
    # 距离观测已经过去 40 分钟，本次冷却检测时间距离上次检测 4.5 分钟 (4.5m < 5.0m, 由于超过 30m，退回默认 base=5m 判定，所以应该被冷却拦截)
    now_timeout_blocked = base_time + timedelta(minutes=40)
    prefs["last_screen_check"] = (base_time + timedelta(minutes=35, seconds=30)).isoformat(timespec="seconds")
    manager.save_preferences(prefs)

    with patch.object(SupervisionEventManager, "_get_active_window_macos", return_value=("Google Chrome", "Steam Community")), \
         patch("memory.supervision_events.datetime") as mock_dt:
        mock_dt.now.return_value = now_timeout_blocked
        mock_dt.fromisoformat.side_effect = datetime.fromisoformat
        mock_dt.combine.side_effect = datetime.combine
        mock_dt.strptime.side_effect = datetime.strptime

        active_events = manager.detect_events(
            focus_state=focus_state,
            commitments=[],
            task_view={},
        )
    # 由于上一次观测超时，自适应频率退回为默认的 5m。当前时间距离 last_screen_check 只有 4.5m，因此被冷却拦截
    deviation_events = [e for e in active_events if e["type"] == "screen_deviation"]
    assert len(deviation_events) == 0
