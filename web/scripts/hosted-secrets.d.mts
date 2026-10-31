export type Rule = [RegExp, string, ((m: RegExpMatchArray) => boolean)?];
export const PUBLIC_OK: Set<string>;
export function hostedEnvProblems(env: Record<string, string | undefined>): string[];
export function hostedRules(env: Record<string, string | undefined>): Rule[];
