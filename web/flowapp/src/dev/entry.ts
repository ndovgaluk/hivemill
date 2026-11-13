// Entry of the development page (index.html, `npm run dev`): read the address, then start the real app.
import { MOUNT_ID } from "../constants";
import { applyAddress } from "./address";

const el = document.getElementById(MOUNT_ID);
if (el && applyAddress(el, window.location.search)) {
  void import("../main");
}
