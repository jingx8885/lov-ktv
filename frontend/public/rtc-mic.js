(function (global) {
  const ICE = [{ urls: "stun:stun.l.google.com:19302" }];

  function newPeerId() {
    return "p" + Math.random().toString(36).slice(2, 10);
  }

  function create(opts) {
    const peerId = (opts && opts.peerId) || newPeerId();
    const role = (opts && opts.role) || "phone";
    let ws = null;
    let pc = null;
    let localStream = null;
    let handlers = {};
    let code = "";
    let closed = false;

    function send(msg) {
      if (ws && ws.readyState === 1) ws.send(JSON.stringify(msg));
    }

    function connect(roomCode, next) {
      code = String(roomCode || "").toUpperCase();
      handlers = next || {};
      closed = false;
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      const url = proto + "//" + location.host + "/ws/rooms/" + encodeURIComponent(code);
      if (ws) {
        try { ws.onclose = null; ws.close(); } catch (err) {}
      }
      ws = new WebSocket(url);
      ws.onopen = () => {
        send({ action: "hello", role, peer: peerId });
        if (handlers.onOpen) handlers.onOpen();
      };
      ws.onmessage = (event) => {
        let msg = null;
        try { msg = JSON.parse(event.data); } catch (err) { return; }
        if (!msg) return;
        if (msg.type === "snapshot" && handlers.onSnapshot) handlers.onSnapshot(msg.room);
        if (msg.type === "peer" && handlers.onPeer) handlers.onPeer(msg);
        if (msg.type === "rtc" && handlers.onRtc) handlers.onRtc(msg);
        if (msg.type === "error" && handlers.onError) handlers.onError(msg);
      };
      ws.onclose = () => {
        if (closed) return;
        setTimeout(() => {
          if (!closed && code) connect(code, handlers);
        }, 1200);
      };
    }

    function disconnect() {
      closed = true;
      if (ws) {
        try { ws.close(); } catch (err) {}
        ws = null;
      }
    }

    async function resetPc() {
      if (pc) {
        try { pc.ontrack = null; pc.onicecandidate = null; pc.close(); } catch (err) {}
        pc = null;
      }
    }

    function bindIce() {
      pc.onicecandidate = (event) => {
        if (event.candidate) {
          send({ action: "rtc", kind: "ice", from: peerId, candidate: event.candidate });
        }
      };
      pc.onconnectionstatechange = () => {
        if (handlers.onState) handlers.onState(pc ? pc.connectionState : "closed");
      };
    }

    async function addIce(msg) {
      if (!pc || !msg || !msg.candidate) return;
      try { await pc.addIceCandidate(msg.candidate); } catch (err) {}
    }

    async function makeOffer() {
      if (!localStream) return;
      await resetPc();
      pc = new RTCPeerConnection({ iceServers: ICE });
      localStream.getTracks().forEach((track) => pc.addTrack(track, localStream));
      bindIce();
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      send({ action: "rtc", kind: "offer", from: peerId, sdp: pc.localDescription });
    }

    async function startMic() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("这台手机不能开麦");
      }
      localStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
        video: false,
      });
      await makeOffer();
      send({ action: "mic", on: true, from: peerId });
      return localStream;
    }

    async function handleAnswer(msg) {
      if (!pc || !msg || !msg.sdp) return;
      if (pc.signalingState === "stable") return;
      await pc.setRemoteDescription(msg.sdp);
    }

    async function handleOffer(msg) {
      if (!msg || !msg.sdp) return;
      await resetPc();
      pc = new RTCPeerConnection({ iceServers: ICE });
      bindIce();
      pc.ontrack = (event) => {
        const stream = event.streams && event.streams[0]
          ? event.streams[0]
          : new MediaStream(event.track ? [event.track] : []);
        if (handlers.onStream) handlers.onStream(stream);
      };
      await pc.setRemoteDescription(msg.sdp);
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      send({ action: "rtc", kind: "answer", from: peerId, sdp: pc.localDescription });
    }

    async function stopMic() {
      if (localStream) {
        localStream.getTracks().forEach((track) => track.stop());
        localStream = null;
      }
      send({ action: "rtc", kind: "hangup", from: peerId });
      send({ action: "mic", on: false, from: peerId });
      await resetPc();
    }

    function isLive() {
      return !!(localStream && localStream.getTracks().some((track) => track.readyState === "live"));
    }

    return {
      peerId,
      connect,
      disconnect,
      send,
      startMic,
      stopMic,
      makeOffer,
      handleAnswer,
      handleOffer,
      addIce,
      resetPc,
      isLive,
    };
  }

  function micErrorText(err) {
    const name = err && err.name;
    const raw = String((err && err.message) || err || "");
    if (name === "NotAllowedError" || /permission|denied|notallowed/i.test(raw)) {
      return "没拿到麦克风权限。系统设置里打开，或用 Safari 打开本页。";
    }
    if (name === "NotFoundError") return "没找到麦克风";
    if (name === "NotReadableError") return "麦克风正被别的 App 占用";
    if (name === "SecurityError" || /getUserMedia|secure|https/i.test(raw)) {
      return "开麦需要安全连接。用 https 打开，或把这页加到主屏幕后再试。";
    }
    return raw || "开麦失败";
  }

  global.LovMic = { create, micErrorText };
})(window);
