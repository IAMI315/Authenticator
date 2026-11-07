import { Box } from "@mui/material";
import appIcon from "../../assets/icon.png";

export function AppIcon({ size }: { size: number }) {
  return <Box component="img" src={appIcon} alt="" sx={{ width: size, height: size, flexShrink: 0, objectFit: "contain" }} />;
}
