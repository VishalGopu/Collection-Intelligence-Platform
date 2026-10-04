from app.agents import specialist_candidate, staffing_snapshot


def test_staffing_counts_unique_scheduled_agents_and_absences(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "agents.csv").write_text(
        "agent_id,agent_display_name,team_id,status,vulnerable_customer_certified,current_case_load,max_concurrent_cases\n"
        "A1,One,T1,active,true,2,10\n"
        "A2,Two,T1,active,false,3,10\n"
        "A3,Three,T2,inactive,true,0,10\n", encoding="utf-8")
    (data / "agent_shifts.csv").write_text(
        "agent_id,shift_date,absence_flag,start_local,end_local,queue_assignment\n"
        "A1,2026-09-28,false,09:00,12:00,hardship_specialist\n"
        "A1,2026-09-28,false,13:00,17:00,hardship_specialist\n"
        "A2,2026-09-28,true,09:00,17:00,mid_stage\n"
        "A3,2026-09-28,false,09:00,17:00,mid_stage\n", encoding="utf-8")

    staffing = staffing_snapshot("2026-09-28", tmp_path)
    assert staffing == {"active_agents": 2, "scheduled_agents": 1,
                        "absent_agents": 1, "scheduled_certified_agents": 1}
    candidate = specialist_candidate("A1", "2026-09-28", tmp_path)
    assert candidate["certified"] is True
    assert candidate["case_load"] == 2
    assert len(candidate["shifts"]) == 2
