"""시험 케이스 메타데이터 레지스트리.

@case("UT-AUTH-01", req="FR-01", title="...", expect="...") 로 테스트 함수에 ID/요구사항/기대결과를
붙이면, scripts/export_cases.py 가 시험계획서(문서) 표를 이 레지스트리에서 생성한다.
→ 문서와 코드의 케이스 ID가 어긋나지 않게 하는 단일 출처(single source of truth).
"""
import pytest

REGISTRY: dict[str, dict] = {}


def case(case_id: str, req: str, title: str, expect: str, kind: str = "positive"):
    """kind: positive(정상) | negative(비정상 입력/예외) | boundary(경계값) | security(보안)"""
    def deco(fn):
        if case_id in REGISTRY and REGISTRY[case_id]["func"] != fn.__qualname__:
            raise ValueError(f"중복 케이스 ID: {case_id}")
        REGISTRY[case_id] = dict(id=case_id, req=req, title=title, expect=expect, kind=kind,
                                 func=fn.__qualname__, module=fn.__module__)
        return pytest.mark.case(case_id)(fn)
    return deco
