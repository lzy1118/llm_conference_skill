package org.grobid.core.engines.tagging;

import java.io.File;
import java.io.IOException;

import com.google.common.base.Joiner;

import org.grobid.core.GrobidModel;
import org.grobid.core.jni.WapitiModel;

public class WapitiTagger implements GenericTagger {

    private final WapitiModel wapitiModel;

    public WapitiTagger(GrobidModel model) {
        wapitiModel = new WapitiModel(model);
    }

    public WapitiTagger(File modelFile) {
        wapitiModel = new WapitiModel(modelFile);
    }

    @Override
    public String label(Iterable<String> data) {
        return label(Joiner.on('\n').join(data));
    }

    @Override
    public String label(String data) {
        return wapitiModel.label(data);
    }

    @Override
    public void close() throws IOException {
        wapitiModel.close();
    }
}
