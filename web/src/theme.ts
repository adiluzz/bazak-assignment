import { theme } from "antd";

export const fontFamily = '"Source Sans 3", "Avenir Next", "Segoe UI", sans-serif';

export function appTheme(dark: boolean) {
  return {
    algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: dark ? "#3cba96" : "#0f6e56",
      colorBgBase: dark ? "#101311" : "#f4f7f5",
      colorBgContainer: dark ? "#181c1a" : "#ffffff",
      colorBgLayout: dark ? "#101311" : "#f4f7f5",
      borderRadius: 16,
      fontFamily,
    },
  };
}
