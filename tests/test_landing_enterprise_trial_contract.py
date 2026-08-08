from pathlib import Path


def test_enterprise_trial_form_uses_the_dedicated_guarded_endpoint():
    index = Path("landing/index.html").read_text(encoding="utf-8")
    app = Path("landing/app.v2.js").read_text(encoding="utf-8")

    assert 'data-action="openEnterpriseTrial"' in index
    assert 'data-field="enterpriseTrialEmail"' in index
    assert 'data-field="enterpriseTrialWebsite"' in index
    assert "fetch('/api/support/enterprise-trial'" in app
    assert "navigator.webdriver === true" in app
    assert "name: 'Enterprise trial request'" not in app
    assert "enterpriseTrialMessage" not in app

