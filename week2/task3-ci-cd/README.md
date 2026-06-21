# Task 3: GitHub Actions CI/CD Pipeline

## What was built
- Automated pipeline: lint -> synth -> deploy on every push
- Two jobs: Validate (always) and Deploy (on main + enabled)

## Pipeline
```
Push to main -> [Validate & Synth] -> [Deploy to AWS]
                  |- flake8 lint        |- AWS credentials
                  |- cdk synth          |- cloudformation update-stack
                  |- upload artifact    |- print outputs
```

## Files
- `.github/workflows/deploy.yml` - Workflow definition
- `.flake8` - Lint config

## Repo
https://github.com/abhi-achar/aws-hands-on-training/actions
