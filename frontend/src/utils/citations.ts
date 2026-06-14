export function formatCitations(text: string, repo?: string): string {
  let result = text;

  result = result.replace(
    /\[Source: Issue #(\d+)\]/g,
    (_match: string, issueId: string) => {
      if (repo && issueId) {
        return `[Issue #${issueId}](https://github.com/${repo}/issues/${issueId})`;
      }
      return `[Issue #${issueId}]`;
    }
  );

  result = result.replace(
    /\[Source: ([^\]]+)\]/g,
    "**[$1]**"
  );

  result = result.replace(
    /\[External Source: (https?:\/\/[^\]]+)\]/g,
    "[External Source]($1)"
  );

  return result;
}
