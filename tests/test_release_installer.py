from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "install.sh").read_text(encoding="utf-8")
IMAGE_COMPOSE = (ROOT / "docker-compose.images.yml").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "release.yml").read_text(
    encoding="utf-8"
)
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def test_release_version_is_consistent() -> None:
    assert f'VERSION="${{PHISHGEN_VERSION:-{VERSION}}}"' in INSTALLER
    assert f"PHISHGEN_VERSION:-{VERSION}" in IMAGE_COMPOSE
    assert f"PHISHGEN_VERSION={VERSION}" in (ROOT / ".env.example").read_text(
        encoding="utf-8"
    )


def test_prebuilt_compose_cannot_pull_or_build() -> None:
    assert "build:" not in IMAGE_COMPOSE
    assert IMAGE_COMPOSE.count("pull_policy: never") == 2
    assert "phishgen_api:${PHISHGEN_VERSION" in IMAGE_COMPOSE
    assert "phishgen_ui:${PHISHGEN_VERSION" in IMAGE_COMPOSE


def test_installer_offers_the_manual_browser_download_first() -> None:
    assert "Download in my browser and paste the file path (recommended)" in INSTALLER
    assert "Download this prebuilt Docker image archive in your browser" in INSTALLER
    assert "Image archive path" in INSTALLER
    assert "--image PATH" in INSTALLER
    assert "docker-compose.images.yml up -d" in INSTALLER


def test_installer_loads_release_images_without_building() -> None:
    assert '"${DOCKER[@]}" load -i "${IMAGE_BUNDLE}"' in INSTALLER
    assert 'images_loaded' in INSTALLER
    assert 'if [ "${IMAGE_MODE}" = "build" ]' in INSTALLER
    assert 'compose -f docker-compose.images.yml up -d' in INSTALLER
    assert "1192073169" in INSTALLER
    assert "6051a375756346c760c0038ba60fe94c2b2b82923c7b36afd70470b9a97b8f79" in INSTALLER


def test_release_publishes_one_archive_containing_both_images() -> None:
    assert 'docker save "phishgen_api:${version}" "phishgen_ui:${version}"' in WORKFLOW
    assert 'phishint-data-generator-images-${version}.tar.gz' in WORKFLOW
    assert "sha256sum \"$archive\"" in WORKFLOW
    assert "docker load -i \"$IMAGE_ARCHIVE\"" in WORKFLOW


def test_script_is_parsed_before_execution() -> None:
    assert "\n{\n" in INSTALLER
    assert INSTALLER.rstrip().endswith("} # end parse-before-execute block")
