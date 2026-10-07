# Repository bundles

A git bundle is an entire repository — every commit, branch and tag — packed
into one file. It is not an archive of the working files; it is the repository
itself, and cloning from it gives back full history.

## ohteapea.bundle

The OhTeaPea product: the email and OTP API on `send.ohteapea.com` and the
dashboard on `app.ohteapea.com`.

Its own remote is `github.com/manojgowda0704/ohteapea`, which was unreachable
from this machine once a second GitHub account's credentials took over. This
bundle exists so the work is not trapped behind that.

### Restoring it

```bash
git clone backups/ohteapea.bundle ohteapea
cd ohteapea
git log --oneline
```

That is a normal repository with the whole history. Point it at a real remote
when you have one:

```bash
git remote set-url origin https://github.com/<owner>/ohteapea.git
git push -u origin main
```

### If you push it somewhere new

The deploy pipeline will not work until the OIDC trust policy is updated.
GitHub issues an immutable subject claim naming the repository, and
`infra/terraform/cicd.tf` pins `github_subject_prefix` to the old one. Read the
new value from the repository's **Settings → Actions → OIDC** page, set it in
that variable, and apply once from CloudShell with `./deploy.sh`. Actions cannot
apply that file itself — it would be granting itself the permission it needs in
order to run.

### Refreshing the bundle

```bash
cd ohteapea && git bundle create ../backups/ohteapea.bundle --all
```

Worth doing whenever that repo has commits its remote does not.
