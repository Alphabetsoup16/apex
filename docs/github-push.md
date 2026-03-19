# Git push issues (GitHub)

## `refusing to allow a Personal Access Token ... workflow ... without workflow scope`

GitHub blocks pushes that add or change files under `.github/workflows/` when you authenticate with a **classic PAT** that does not include the **`workflow`** scope.

### Fix (classic PAT)

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens**
2. Edit your token (or create a new one)
3. Enable scope: **`workflow`** (updates GitHub Action workflows)
4. Use the new token with HTTPS (`git push`), or update the credential helper / macOS Keychain entry

### Fix (fine-grained PAT)

Include permission for **Actions** (read/write) or whatever your org requires for modifying workflow files.

### Alternative: SSH

If you use **SSH** (`git@github.com:...`) with an SSH key attached to your account, you are not limited by PAT workflow scope the same way. Ensure `git remote -v` uses the SSH URL if you switch:

```bash
git remote set-url origin git@github.com:Alphabetsoup16/apex.git
```

### Verify

```bash
git push origin main
```
