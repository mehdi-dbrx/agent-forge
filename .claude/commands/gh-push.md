Push current project changes to GitHub.

1. Run `git status` to see what has changed.
2. If there are changes (modified, new, or deleted files), stage all of them with `git add .`
3. Create a commit with a concise message describing the changes. Always append the co-author trailer:
   ```
   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
   ```
4. Run `git push`.
5. Report what was committed and pushed. If there was nothing to commit, say so.
