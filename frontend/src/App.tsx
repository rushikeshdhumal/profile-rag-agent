import { Route, Routes } from "react-router-dom";
import BuilderPage from "./pages/BuilderPage";
import ChatPage from "./pages/ChatPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<BuilderPage />} />
      <Route path="/a/:agentId" element={<ChatPage />} />
    </Routes>
  );
}
