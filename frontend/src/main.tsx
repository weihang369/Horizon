// Entry. Owner: EE. Global CSS + fonts come from the VMD's styles/ (R18: Latin subsets).
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles";
import "./index.css";
import "./stores/prefs";
import { App } from "./app/App";

document.title = "Horizon";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
