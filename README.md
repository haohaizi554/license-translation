# 执照英译

把中国 **A 格式公司法人营业执照** 照片转成固定英文模板 PDF（第 1 页译文，第 2 页原件）。个体户、合伙、合作社、分公司会拒绝转换。

## 运行

```powershell
pip install -r requirements.txt
python gui.py
```

命令行：

```powershell
python batch.py samples/input.jpeg -o out --issue-date 2022-12-09
```

红章月份经常识别不到，可在面板勾选「指定发证日期」，或用 `--issue-date`。

## 资源

模板只用 `assets/` 里三张图：国徽、翻译专用章、签名。`samples/input.jpeg` 为样张。
