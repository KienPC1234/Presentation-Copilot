"""Real-model reviewer calibration on controlled synthetic counterexamples.

This tests the verifier, not project retrieval, speech or meeting accuracy.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
from threading import local


def answer(point, *steps):
    return {"key_point": point, "keywords": [], "framework_steps": list(steps)}


API = "case 'status': return {'completed': bool(saved), 'result': saved}; case 'commit': if saved: return {'replayed': True, 'result': saved};"
DEADLINE = "if(now > deadline + 15) { answers = draft.answers; } else { answers = request.answers; }"
ATOMICITY = ["save_draft: UPSERT drafts ON (user_id, exam_id).", "commit_result: if saved: return replayed. Final result persistence code is not supplied."]
CASES = [
    {"id": "wrong_action", "question": "status trả về gì, có trả replayed không?", "parts": ["Nêu trường trả về của status và phân biệt replayed"],
     "evidence": [API], "candidate": answer("status trả replayed=true nếu đã có kết quả."), "expected": "reject"},
    {"id": "valid_action", "question": "status trả về gì, khác commit thế nào?", "parts": ["Trường trả về của status", "Phân biệt commit"],
     "evidence": [API], "candidate": answer("Theo mã, status trả completed và result; nhánh commit mới trả replayed khi đã có kết quả."), "expected": "accept"},
    {"id": "wrong_atomicity", "question": "Đã chứng minh commit_result ghi một lần khi hai yêu cầu đồng thời chưa?", "parts": ["Phân biệt ý định replay và bằng chứng an toàn đồng thời"],
     "evidence": ATOMICITY, "candidate": answer("Đã chứng minh commit_result ghi nguyên tử đúng một lần vì save_draft có UPSERT."), "expected": "reject"},
    {"id": "valid_atomicity_unknown", "question": "Đã chứng minh commit_result ghi một lần khi hai yêu cầu đồng thời chưa?", "parts": ["Phân biệt ý định replay và bằng chứng an toàn đồng thời"],
     "evidence": ATOMICITY, "candidate": answer("Chưa chứng minh: chỉ có nhánh replay và upsert bản nháp; chưa có mã lưu kết quả cuối hoặc phép thử đồng thời."), "expected": "accept"},
    {"id": "wrong_deadline", "question": "Sau deadline 15 giây dùng câu trả lời nào?", "parts": ["Hành vi khi now > deadline + 15"],
     "evidence": [DEADLINE], "candidate": answer("Sau deadline 15 giây, hệ thống trả lỗi và không dùng câu trả lời nào."), "expected": "reject"},
    {"id": "valid_deadline", "question": "Sau deadline 15 giây dùng câu trả lời nào?", "parts": ["Hành vi khi now > deadline + 15"],
     "evidence": [DEADLINE], "candidate": answer("Theo đoạn mã, khi now > deadline + 15 thì dùng answers của bản nháp; nếu không thì dùng answers trong yêu cầu."), "expected": "accept"},
    {"id": "missing_changed_id", "question": "Đề xuất thử quyền sở hữu, sửa ID để thử truy cập trái phép và bằng chứng cần thu.",
     "parts": ["Thử quyền sở hữu", "Sửa ID để thử truy cập trái phép", "Bằng chứng cần thu"], "evidence": [],
     "candidate": answer("Đề xuất dùng hai tài khoản thử quyền sở hữu.", "Đề xuất gửi lại cùng khóa và ghi log phản hồi."), "expected": "reject"},
    {"id": "valid_changed_id_test", "question": "Đề xuất thử quyền sở hữu, sửa ID để thử truy cập trái phép và bằng chứng cần thu.",
     "parts": ["Thử quyền sở hữu", "Sửa ID để thử truy cập trái phép", "Bằng chứng cần thu"], "evidence": [],
     "candidate": answer("Đề xuất kiểm thử bằng hai tài khoản A và B, mỗi tài khoản có dữ liệu riêng.",
                         "Đề xuất: A thay ID trong yêu cầu thành ID dữ liệu của B rồi thử đọc và sửa; phải bị từ chối, dữ liệu B không đổi. Đối chiếu với yêu cầu hợp lệ của B.",
                         "Đề xuất thu request/response, tài khoản, thời điểm và dữ liệu B trước/sau; đây là kế hoạch thử, chưa phải kết quả đã đo."), "expected": "accept"},
    {"id": "wrong_status_precondition", "question": "Kiểm thử khóa đúng định dạng nhưng thuộc người dùng khác; có thể kỳ vọng chính xác mã lỗi nào theo bằng chứng?",
     "parts": ["Phân biệt lỗi định dạng và truy cập dữ liệu của người khác"],
     "evidence": ["status(key, user): if malformed(key): return HTTP 422; else: return lookup(user, key). Implementation of lookup is not supplied."],
     "candidate": answer("Đề xuất dùng khóa hợp lệ của người khác; chắc chắn nhận HTTP 422 theo mã nguồn."), "expected": "reject"},
    {"id": "invented_sla_in_proposal", "question": "Nêu điều kiện triển khai từ bằng chứng, không tự đặt ngưỡng.", "parts": ["Điều kiện triển khai có căn cứ"],
     "evidence": ["No latency benchmark or numerical SLA is supplied."],
     "candidate": answer("Đề xuất triển khai khi độ trễ dưới 2s."), "expected": "reject"},
    {"id": "wrong_design_rationale", "question": "Vì sao tác giả chọn bỏ qua mã truy cập khi có bản nháp? Chỉ nêu lý do được tài liệu giải thích.",
     "parts": ["Lý do thiết kế được tài liệu giải thích, hoặc thừa nhận chưa biết"], "evidence": ["if(hasDraft) { skipAccessCode(); }"],
     "candidate": answer("Tác giả thiết kế như vậy để giúp người dùng tiếp tục làm bài thuận tiện."), "expected": "reject"},
    {"id": "valid_design_unknown", "question": "Vì sao tác giả chọn bỏ qua mã truy cập khi có bản nháp? Chỉ nêu lý do được tài liệu giải thích.",
     "parts": ["Lý do thiết kế được tài liệu giải thích, hoặc thừa nhận chưa biết"], "evidence": ["if(hasDraft) { skipAccessCode(); }"],
     "candidate": answer("Mã cho thấy có bản nháp thì bỏ qua mã truy cập, nhưng không giải thích lý do tác giả chọn thiết kế này."), "expected": "accept"},
    {"id": "wrong_blanket_false_summary", "question": "Đối chiếu hai khẳng định: dùng ZetaDB và tự trừ điểm khi rời tab.",
     "parts": ["Dùng ZetaDB", "Tự trừ điểm khi rời tab"],
     "evidence": ["No storage technology is documented. Leaving the tab records a signal for human review, without automatic score deductions."],
     "candidate": answer("Cả hai khẳng định đều sai.", "Việc dùng ZetaDB chưa được xác lập.", "Rời tab không tự trừ điểm theo tài liệu."), "expected": "reject"},
    {"id": "valid_distinct_uncertainty", "question": "Đối chiếu hai khẳng định: dùng ZetaDB và tự trừ điểm khi rời tab.",
     "parts": ["Dùng ZetaDB", "Tự trừ điểm khi rời tab"],
     "evidence": ["No storage technology is documented. Leaving the tab records a signal for human review, without automatic score deductions."],
     "candidate": answer("Việc dùng ZetaDB chưa được tài liệu xác nhận; còn khẳng định rời tab tự trừ điểm trái với mô tả tài liệu."), "expected": "accept"},
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=[c["id"] for c in CASES])
    parser.add_argument("--trace", action="store_true", help="Include final reviewer JSON for synthetic calibration diagnostics")
    args = parser.parse_args()
    from services.ollama_json import OllamaJSONClient
    from services.grounding_review import review_grounding
    provider = OllamaJSONClient(args.review_model, num_predict=8192)
    state = local()

    class Recorder:
        def invoke(self, messages):
            result = provider.invoke(messages)
            state.raw = result.content
            return result

    llm = Recorder()

    def evaluate(case):
        requirements = [{"id": f"r{i}", "request": part} for i, part in enumerate(case["parts"], 1)]
        started = time.perf_counter()
        state.raw = None
        try:
            issues = review_grounding(llm, case["question"], case["candidate"], case["evidence"], [], requirements)
            outcome = "reject" if issues else "accept"
            result = {"id": case["id"], "expected": case["expected"], "outcome": outcome, "matched": outcome == case["expected"],
                      "issues": issues, "seconds": round(time.perf_counter()-started, 2)}
        except Exception as exc:
            result = {"id": case["id"], "expected": case["expected"], "outcome": "provider_or_schema_error",
                      "matched": False, "error": f"{type(exc).__name__}: {exc}", "seconds": round(time.perf_counter()-started, 2)}
        if args.trace:
            result["review_json"] = state.raw
        result["reviewer_called"] = state.raw is not None
        return result

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(evaluate, [c for c in CASES if not args.case or c["id"] == args.case]))
    report = {"scope": __doc__, "model": args.review_model, "results": results,
              "all_matched": all(result["matched"] for result in results)}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    if not report["all_matched"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
