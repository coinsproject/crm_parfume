// Минимальные заглушки для React/JSX, чтобы подавить TS-ошибки без установленного React.
declare module "react" {
  export type ReactNode = any;
  export type FC<P = any> = (props: P) => any;
  export const useEffect: any;
  export const useMemo: any;
  export const useState: any;
  const _default: any;
  export default _default;
}

declare module "react/jsx-runtime" {
  export const jsx: any;
  export const jsxs: any;
  export const Fragment: any;
}

declare global {
  namespace JSX {
    interface IntrinsicElements {
      [elemName: string]: any;
    }
  }
}
