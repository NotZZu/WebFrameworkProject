"""도구 시험: 배포 설정 파일(deploy/) — 문법과 핵심 설정 점검. 실제 AWS 에 올리기 전에 CI 에서 먼저 걸러낸다."""
import pathlib
import subprocess

import pytest

yaml = pytest.importorskip("yaml")
DEPLOY = pathlib.Path(__file__).resolve().parents[3] / "deploy"
pytestmark = pytest.mark.skipif(not DEPLOY.exists(), reason="배포 파일(deploy/) 없음")


class _Loader(yaml.SafeLoader):
    pass


# CloudFormation 단축 태그(!Ref, !Sub, !GetAtt …)를 일반 값으로 읽는다.
_Loader.add_multi_constructor("!", lambda loader, suffix, node: (
    loader.construct_scalar(node) if isinstance(node, yaml.ScalarNode)
    else loader.construct_sequence(node) if isinstance(node, yaml.SequenceNode)
    else loader.construct_mapping(node)))


def load(name):
    return yaml.load((DEPLOY / name).read_text(encoding="utf-8"), Loader=_Loader)


def test_cloudformation_has_required_resources_and_outputs():
    t = load("cloudformation.yml")
    types = {r["Type"] for r in t["Resources"].values()}
    assert {"AWS::EC2::Instance", "AWS::EC2::SecurityGroup", "AWS::EC2::EIP", "AWS::EC2::EIPAssociation"} <= types
    assert {"ServiceUrl", "DemoUrl"} <= set(t["Outputs"])
    assert t["Parameters"]["InstanceType"]["Default"] == "t3.micro"


def test_security_group_exposes_only_web_ports_not_ssh():
    sg = load("cloudformation.yml")["Resources"]["AppSecurityGroup"]["Properties"]["SecurityGroupIngress"]
    assert sorted(r["FromPort"] for r in sg) == [80, 8080]


def test_instance_requires_imdsv2():
    inst = load("cloudformation.yml")["Resources"]["AppInstance"]["Properties"]
    assert inst["MetadataOptions"]["HttpTokens"] == "required"


def test_compose_runs_service_and_demo_separately():
    c = load("docker-compose.yml")["services"]
    assert set(c) == {"service", "demo"}
    assert c["service"]["ports"] == ["80:8000"] and c["demo"]["ports"] == ["8080:8000"]
    assert "/data" in c["service"]["volumes"][0]          # 서비스 DB 는 볼륨에 보존
    assert not c["demo"].get("volumes")                    # 시연 서버는 서비스 데이터에 접근하지 않음


@pytest.mark.parametrize("script", ["bootstrap.sh", "update.sh"])
def test_shell_scripts_have_valid_syntax(script):
    r = subprocess.run(["bash", "-n", str(DEPLOY / script)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_no_secret_values_committed():
    text = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in DEPLOY.iterdir() if p.is_file())
    assert "AKIA" not in text and "aws_secret_access_key" not in text.lower()


def test_cloudformation_serves_https_via_cloudfront():
    t = load("cloudformation.yml")
    cdn = [r for r in t["Resources"].values() if r["Type"] == "AWS::CloudFront::Distribution"]
    assert len(cdn) == 2
    for c in cdn:
        b = c["Properties"]["DistributionConfig"]["DefaultCacheBehavior"]
        assert b["ViewerProtocolPolicy"] == "redirect-to-https"


def test_cloudformation_has_budget_guard_that_stops_ec2():
    t = load("cloudformation.yml")
    types = {r["Type"] for r in t["Resources"].values()}
    assert {"AWS::Budgets::Budget", "AWS::Budgets::BudgetsAction"} <= types
    act = t["Resources"]["BudgetStopAction"]["Properties"]
    assert act["Definition"]["SsmActionDefinition"]["Subtype"] == "STOP_EC2_INSTANCES"


def test_demo_reads_service_url_from_env_file():
    c = load("docker-compose.yml")
    assert c["services"]["demo"]["env_file"] == ["service.env"]
    assert (DEPLOY / "service.env").exists()


def test_demo_image_includes_deploy_files():
    """시연 이미지에 deploy/ 가 들어가야 이 파일의 시험이 시연 화면에서 건너뛰어지지 않는다."""
    assert "COPY deploy /app/deploy" in (DEPLOY / "Dockerfile.demo").read_text(encoding="utf-8")
